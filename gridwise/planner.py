"""Deterministic charging-window planner.

The LLM never does this arithmetic. It calls a tool, and the tool calls this
module. That keeps answers reproducible and testable.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Literal

from .eds_client import Co2Point, PricePoint

Priority = Literal["cheapest", "greenest", "balanced"]
SLOT = timedelta(minutes=15)
PRICE_WEIGHT: dict[str, float] = {"cheapest": 1.0, "greenest": 0.0, "balanced": 0.5}
MIN_CO2_COVERAGE = 0.8  # share of slots in a window that need a CO2 value


@dataclass(frozen=True)
class Slot:
    start: datetime
    dkk_per_kwh: float
    co2_g_per_kwh: float | None


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime
    avg_dkk_per_kwh: float
    avg_co2_g_per_kwh: float | None
    est_spot_cost_dkk: float
    est_co2_kg: float | None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["start"] = self.start.strftime("%a %d %b %H:%M")
        d["end"] = self.end.strftime("%a %d %b %H:%M")
        return d


@dataclass(frozen=True)
class Plan:
    recommended: Window
    cheapest: Window
    greenest: Window | None
    baseline: Window  # starting at the earliest allowed time, i.e. "plug in and charge now"
    priority: str
    duration_minutes: int
    kwh: float
    notes: list[str]

    def to_dict(self) -> dict:
        saving_dkk = round(self.baseline.est_spot_cost_dkk - self.recommended.est_spot_cost_dkk, 2)
        co2_saving = None
        if self.baseline.est_co2_kg is not None and self.recommended.est_co2_kg is not None:
            co2_saving = round(self.baseline.est_co2_kg - self.recommended.est_co2_kg, 2)
        return {
            "priority": self.priority,
            "kwh": self.kwh,
            "duration_minutes": self.duration_minutes,
            "recommended": self.recommended.to_dict(),
            "cheapest": self.cheapest.to_dict(),
            "greenest": self.greenest.to_dict() if self.greenest else None,
            "baseline_charge_immediately": self.baseline.to_dict(),
            "spot_saving_vs_baseline_dkk": saving_dkk,
            "co2_saving_vs_baseline_kg": co2_saving,
            "notes": self.notes,
        }


def merge(prices: list[PricePoint], co2: list[Co2Point]) -> list[Slot]:
    """Join 15-minute prices with 15-minute CO2 forecast on slot start time."""
    co2_by_start = {c.start: c.g_per_kwh for c in co2}
    return [Slot(p.start, p.dkk_per_kwh, co2_by_start.get(p.start)) for p in prices]


def _windows(slots: list[Slot], n: int, kwh: float) -> list[Window]:
    out = []
    for i in range(len(slots) - n + 1):
        run = slots[i : i + n]
        # contiguous only: an EV charging session should not be split
        if run[-1].start - run[0].start != SLOT * (n - 1):
            continue
        avg_price = sum(s.dkk_per_kwh for s in run) / n
        co2_vals = [s.co2_g_per_kwh for s in run if s.co2_g_per_kwh is not None]
        avg_co2 = sum(co2_vals) / len(co2_vals) if len(co2_vals) >= MIN_CO2_COVERAGE * n else None
        out.append(
            Window(
                start=run[0].start,
                end=run[-1].start + SLOT,
                avg_dkk_per_kwh=round(avg_price, 4),
                avg_co2_g_per_kwh=round(avg_co2, 1) if avg_co2 is not None else None,
                est_spot_cost_dkk=round(avg_price * kwh, 2),
                est_co2_kg=round(avg_co2 * kwh / 1000, 2) if avg_co2 is not None else None,
            )
        )
    return out


def _norm(values: list[float]) -> list[float]:
    lo, hi = min(values), max(values)
    if math.isclose(lo, hi):
        return [0.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def plan_charging(
    slots: list[Slot],
    kwh: float,
    charger_kw: float,
    earliest: datetime,
    latest: datetime,
    priority: Priority = "balanced",
) -> Plan:
    """Find the best contiguous charging window between ``earliest`` and ``latest``.

    ``latest`` is the time the car must be finished (e.g. leaving for work).
    """
    if kwh <= 0 or charger_kw <= 0:
        raise ValueError("kwh and charger_kw must be positive")
    if priority not in PRICE_WEIGHT:
        raise ValueError("priority must be cheapest, greenest or balanced")

    n = max(1, math.ceil(kwh / charger_kw * 4))  # number of 15-min slots needed
    notes: list[str] = []
    usable = [s for s in slots if earliest <= s.start and s.start + SLOT <= latest]
    if len(usable) < n:
        hours = n / 4
        raise ValueError(
            f"Charging {kwh} kWh at {charger_kw} kW needs {hours:g} h, but only "
            f"{len(usable) / 4:g} h of priced time is available in that window."
        )

    windows = _windows(usable, n, kwh)
    if not windows:
        raise ValueError("No contiguous window of the required length in the available data.")

    cheapest = min(windows, key=lambda w: w.avg_dkk_per_kwh)
    with_co2 = [w for w in windows if w.avg_co2_g_per_kwh is not None]
    greenest = min(with_co2, key=lambda w: w.avg_co2_g_per_kwh) if with_co2 else None

    weight = PRICE_WEIGHT[priority]
    if not with_co2:
        if priority != "cheapest":
            notes.append("CO2 forecast not available for this period, so the plan is price-only.")
        recommended = cheapest
    else:
        price_n = _norm([w.avg_dkk_per_kwh for w in with_co2])
        co2_n = _norm([w.avg_co2_g_per_kwh for w in with_co2])  # type: ignore[misc]
        scores = [weight * p + (1 - weight) * c for p, c in zip(price_n, co2_n, strict=True)]
        recommended = with_co2[scores.index(min(scores))]
        if len(with_co2) < len(windows):
            notes.append("Some windows had no CO2 forecast and were only considered for 'cheapest'.")

    baseline = windows[0]
    notes.append(
        "Prices are day-ahead spot only. Your bill also includes grid tariff "
        "(highest 17:00-21:00), electricity tax and VAT."
    )
    return Plan(
        recommended=recommended,
        cheapest=cheapest,
        greenest=greenest,
        baseline=baseline,
        priority=priority,
        duration_minutes=n * 15,
        kwh=kwh,
        notes=notes,
    )
