"""Thin client for Energinet's Energi Data Service (EDS).

Two datasets are used:

* ``DayAheadPrices``: day-ahead spot prices per bidding zone. Since 1 Oct 2025
  the Nordic day-ahead market settles in 15-minute periods (MTU), so this
  dataset has four rows per hour. It replaced the hourly ``Elspotprices``
  dataset, which stops at 30 Sep 2025.
* ``CO2EmisProg``: forecast CO2 intensity of consumed electricity
  (g CO2/kWh) in 5-minute resolution.

The API is free, needs no key, and allows roughly 50 calls per 10 seconds per IP.
Docs: https://www.energidataservice.dk/guides/api-guides
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

BASE_URL = "https://api.energidataservice.dk/dataset"
DK_TZ = ZoneInfo("Europe/Copenhagen")
PRICE_AREAS = {"DK1": "West Denmark (Jutland, Funen)", "DK2": "East Denmark (Zealand, Copenhagen)"}
SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data"
MAX_ATTEMPTS = 3
MAX_WAIT_SECONDS = 15  # wait and retry if EDS asks for at most this long; otherwise tell the user
CACHE_SECONDS = 900  # prices change once a day; caching keeps us inside the per-dataset rate limits
USER_AGENT = "GridWise/0.1 (+https://github.com/mahrukhzulfiqar/gridwise)"
_CACHE: dict[tuple[str, str, date], tuple[float, list[dict]]] = {}


class EDSError(RuntimeError):
    """Raised when Energi Data Service cannot be reached or returns bad data."""


@dataclass(frozen=True)
class PricePoint:
    start: datetime  # timezone-aware, Europe/Copenhagen
    dkk_per_kwh: float  # spot only: excl. grid tariff, taxes and VAT
    eur_per_mwh: float


@dataclass(frozen=True)
class Co2Point:
    start: datetime  # timezone-aware, Europe/Copenhagen
    g_per_kwh: float


def _offline() -> bool:
    return os.getenv("GRIDWISE_OFFLINE", "").lower() in {"1", "true", "yes"}


def _validate_area(area: str) -> str:
    area = area.upper().strip()
    if area not in PRICE_AREAS:
        raise ValueError(f"Unknown price area '{area}'. Use DK1 or DK2.")
    return area


def _parse_utc(value: str) -> datetime:
    """EDS timestamps are naive ISO strings; the *UTC columns are UTC."""
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).astimezone(DK_TZ)


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=DK_TZ)
    nxt = day + timedelta(days=1)
    end = datetime(nxt.year, nxt.month, nxt.day, tzinfo=DK_TZ)
    return start, end


def _fetch(dataset: str, area: str, day: date, sort_col: str, client: httpx.Client | None = None) -> list[dict]:
    """Fetch one Danish calendar day of a dataset for one price area.

    Energi Data Service applies per-dataset rate limits, so we make one call for
    the requested day *and* the next day, and cache both. A planner that needs
    today and tomorrow then costs one call per dataset instead of two.

    We ask for a slightly wider UTC window and filter locally on the UTC column,
    so the result is correct on DST change days regardless of how the API
    interprets start/end.
    """
    if _offline():
        return _load_sample(dataset, area, day)

    use_cache = client is None  # tests pass their own mock client and bypass the cache
    cached = _CACHE.get((dataset, area, day))
    if use_cache and cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]

    days = [day, day + timedelta(days=1)]
    start, _ = _day_bounds(days[0])
    _, end = _day_bounds(days[-1])
    params = {
        "start": (start - timedelta(hours=3)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M"),
        "end": (end + timedelta(hours=3)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M"),
        "timezone": "UTC",
        "filter": json.dumps({"PriceArea": [area]}),
        "sort": f"{sort_col} asc",
        "limit": "2000",  # two days are at most ~720 rows; avoid unbounded queries
    }
    owns_client = client is None
    client = client or httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT})
    try:
        payload = _get_with_retry(client, f"{BASE_URL}/{dataset}", params, dataset)
    finally:
        if owns_client:
            client.close()

    records = payload.get("records")
    if records is None:
        raise EDSError(f"Unexpected response from {dataset}: no 'records' field")

    now = time.monotonic()
    result: list[dict] = []
    for d in days:
        d_start, d_end = _day_bounds(d)
        rows = [r for r in records if d_start <= _parse_utc(r[sort_col]) < d_end]
        if use_cache:
            _CACHE[(dataset, area, d)] = (now, rows)
        if d == day:
            result = rows
    return result


def _wait_seconds(resp: httpx.Response) -> float | None:
    """How long EDS asks us to wait: Retry-After header or 'Try again in X seconds' in the body."""
    header = resp.headers.get("Retry-After", "")
    if header.isdigit():
        return float(header)
    match = re.search(r"try again in (\d+) seconds?", resp.text, re.IGNORECASE)
    return float(match.group(1)) if match else None


def _get_with_retry(client: httpx.Client, url: str, params: dict, dataset: str) -> dict:
    """GET with polite retries. EDS answers 429 when called too often, and 5xx on hiccups."""
    for attempt in range(MAX_ATTEMPTS):
        try:
            resp = client.get(url, params=params)
        except httpx.HTTPError as exc:
            if attempt == MAX_ATTEMPTS - 1:
                raise EDSError(f"Could not reach Energi Data Service ({dataset}): {exc}") from exc
            time.sleep(2**attempt)
            continue
        if resp.status_code == 429:
            wait = _wait_seconds(resp)
            if attempt == MAX_ATTEMPTS - 1 or (wait is not None and wait > MAX_WAIT_SECONDS):
                when = f"in about {int(wait)} seconds" if wait else "in a minute"
                raise EDSError(f"Energi Data Service is limiting requests for {dataset}. Try again {when}.")
            time.sleep((wait or 2 ** (attempt + 1)) + 0.5)
            continue
        if resp.status_code >= 500:
            if attempt == MAX_ATTEMPTS - 1:
                raise EDSError(f"Energi Data Service is having problems (HTTP {resp.status_code}). Try again later.")
            time.sleep(2 ** (attempt + 1))
            continue
        try:
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EDSError(f"Energi Data Service request for {dataset} failed: {exc}") from exc
    raise EDSError(f"Energi Data Service request for {dataset} failed")  # pragma: no cover


def _load_sample(dataset: str, area: str, day: date) -> list[dict]:
    """Offline mode: replay a bundled sample day, shifted onto the requested date."""
    path = SAMPLE_DIR / f"sample_{dataset}.json"
    records = json.loads(path.read_text())["records"]
    utc_col = "TimeUTC" if dataset == "DayAheadPrices" else "Minutes5UTC"
    first = _parse_utc(records[0][utc_col]).date()
    shift = day - first  # timedelta of whole days
    out = []
    for r in records:
        r = dict(r, PriceArea=area)
        t = datetime.fromisoformat(r[utc_col]) + shift
        r[utc_col] = t.isoformat(timespec="seconds")
        out.append(r)
    return out


def get_day_ahead_prices(area: str, day: date, client: httpx.Client | None = None) -> list[PricePoint]:
    """15-minute spot prices for one Danish calendar day. Empty list if not yet published."""
    area = _validate_area(area)
    rows = _fetch("DayAheadPrices", area, day, "TimeUTC", client)
    points = []
    for r in rows:
        dkk_mwh = r.get("DayAheadPriceDKK")
        if dkk_mwh is None:
            continue
        points.append(
            PricePoint(
                start=_parse_utc(r["TimeUTC"]),
                dkk_per_kwh=round(dkk_mwh / 1000, 4),
                eur_per_mwh=r.get("DayAheadPriceEUR") or 0.0,
            )
        )
    return sorted(points, key=lambda p: p.start)


def get_co2_forecast(area: str, day: date, client: httpx.Client | None = None) -> list[Co2Point]:
    """CO2 intensity forecast (g/kWh), averaged from 5-minute to 15-minute slots."""
    area = _validate_area(area)
    rows = _fetch("CO2EmisProg", area, day, "Minutes5UTC", client)
    buckets: dict[datetime, list[float]] = {}
    for r in rows:
        if r.get("CO2Emission") is None:
            continue
        t = _parse_utc(r["Minutes5UTC"])
        slot = t.replace(minute=t.minute - t.minute % 15, second=0, microsecond=0)
        buckets.setdefault(slot, []).append(float(r["CO2Emission"]))
    return [Co2Point(start=k, g_per_kwh=round(sum(v) / len(v), 1)) for k, v in sorted(buckets.items())]
