"""GridWise MCP server.

Exposes Danish electricity prices, CO2 forecast and an EV charging planner as
MCP tools. Works with any MCP client: the bundled Streamlit app, Claude Desktop,
or your own agent.

Run over stdio:  python -m gridwise.server
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Literal

from mcp.server.mcpserver import MCPServer

from . import eds_client as eds
from .planner import SLOT, merge, plan_charging

DayArg = str  # "today", "tomorrow" or YYYY-MM-DD
PUBLISH_NOTE = (
    "Day-ahead prices for tomorrow are normally published early afternoon "
    "(around 13:00 Danish time). Try again later or ask about today."
)

mcp = MCPServer(
    "GridWise",
    instructions=(
        "Tools for Danish electricity: day-ahead spot prices and CO2 intensity "
        "forecast from Energinet's Energi Data Service, plus an EV charging planner. "
        "DK1 = West Denmark (Jutland, Funen). DK2 = East Denmark (Zealand, Copenhagen). "
        "Always use plan_ev_charging for charging-time questions instead of doing the maths yourself. "
        "Prices are spot only; say so when quoting them."
    ),
    version="0.1.0",
)


def _now() -> datetime:
    return datetime.now(eds.DK_TZ)


def _resolve_day(day: DayArg) -> date:
    today = _now().date()
    key = day.strip().lower()
    if key in {"", "today", "i dag"}:
        return today
    if key in {"tomorrow", "i morgen"}:
        return today + timedelta(days=1)
    try:
        return date.fromisoformat(key)
    except ValueError as exc:
        raise ValueError("day must be 'today', 'tomorrow' or YYYY-MM-DD") from exc


def _parse_hhmm(value: str) -> time:
    try:
        return time.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"'{value}' is not a valid time, use HH:MM") from exc


def _hourly(points: list, attr: str) -> list[dict]:
    hours: dict[datetime, list[float]] = {}
    for p in points:
        hours.setdefault(p.start.replace(minute=0), []).append(getattr(p, attr))
    return [{"hour": h.strftime("%H:%M"), "avg": round(sum(v) / len(v), 3)} for h, v in sorted(hours.items())]


@mcp.tool(
    description=(
        "Day-ahead spot prices (DKK/kWh, excl. tariffs, taxes and VAT) for a Danish price area, summarised per hour."
    )
)
def get_prices(area: Literal["DK1", "DK2"] = "DK2", day: DayArg = "today") -> dict:
    d = _resolve_day(day)
    prices = eds.get_day_ahead_prices(area, d)
    if not prices:
        return {"area": area, "date": d.isoformat(), "published": False, "note": PUBLISH_NOTE}
    lo = min(prices, key=lambda p: p.dkk_per_kwh)
    hi = max(prices, key=lambda p: p.dkk_per_kwh)
    return {
        "area": area,
        "date": d.isoformat(),
        "published": True,
        "unit": "DKK/kWh, spot only",
        "resolution_minutes": 15,
        "hourly": _hourly(prices, "dkk_per_kwh"),
        "cheapest_quarter": {"start": lo.start.strftime("%H:%M"), "dkk_per_kwh": lo.dkk_per_kwh},
        "most_expensive_quarter": {"start": hi.start.strftime("%H:%M"), "dkk_per_kwh": hi.dkk_per_kwh},
        "daily_average": round(sum(p.dkk_per_kwh for p in prices) / len(prices), 3),
    }


@mcp.tool(description="Forecast CO2 intensity (g CO2/kWh) of electricity in a Danish price area, summarised per hour.")
def get_co2_forecast(area: Literal["DK1", "DK2"] = "DK2", day: DayArg = "today") -> dict:
    d = _resolve_day(day)
    co2 = eds.get_co2_forecast(area, d)
    if not co2:
        return {"area": area, "date": d.isoformat(), "available": False, "note": "No CO2 forecast for this day yet."}
    lo = min(co2, key=lambda c: c.g_per_kwh)
    return {
        "area": area,
        "date": d.isoformat(),
        "available": True,
        "unit": "g CO2/kWh",
        "hourly": _hourly(co2, "g_per_kwh"),
        "greenest_quarter": {"start": lo.start.strftime("%H:%M"), "g_per_kwh": lo.g_per_kwh},
    }


@mcp.tool(
    description=(
        "Plan when to charge an EV. Finds the best continuous charging window between "
        "plug-in time and ready-by time, by price, CO2 or a balance of both. "
        "Compares it with charging immediately at plug-in."
    )
)
def plan_ev_charging(
    kwh: float,
    area: Literal["DK1", "DK2"] = "DK2",
    charger_kw: float = 11.0,
    plug_in_day: DayArg = "today",
    plug_in_time: str = "17:00",
    ready_by: str = "07:00",
    priority: Literal["cheapest", "greenest", "balanced"] = "balanced",
) -> dict:
    """kwh: energy to add. ready_by is on the next day if it is not after plug_in_time."""
    d = _resolve_day(plug_in_day)
    earliest = datetime.combine(d, _parse_hhmm(plug_in_time), tzinfo=eds.DK_TZ)
    latest = datetime.combine(d, _parse_hhmm(ready_by), tzinfo=eds.DK_TZ)
    if latest <= earliest:
        latest = datetime.combine(d + timedelta(days=1), _parse_hhmm(ready_by), tzinfo=eds.DK_TZ)

    now = _now()
    if earliest < now:  # cannot charge in the past: start at the next quarter hour
        earliest = now.replace(second=0, microsecond=0) + timedelta(minutes=15 - now.minute % 15)

    days = sorted({earliest.date(), (latest - SLOT).date()})
    prices, co2 = [], []
    for day_ in days:
        prices += eds.get_day_ahead_prices(area, day_)
        co2 += eds.get_co2_forecast(area, day_)

    try:
        plan = plan_charging(merge(prices, co2), kwh, charger_kw, earliest, latest, priority)
    except ValueError as exc:
        published_until = max((p.start for p in prices), default=None)
        if published_until is None or published_until + SLOT < latest:
            return {"planned": False, "reason": str(exc), "note": PUBLISH_NOTE}
        return {"planned": False, "reason": str(exc)}
    result = {"planned": True, "area": area, **plan.to_dict()}
    published_until = max(p.start for p in prices) + SLOT
    if published_until < latest:
        result["notes"].append(
            f"Prices are only published until {published_until:%a %H:%M}, so later hours were not considered. "
            + PUBLISH_NOTE
        )
    return result


def main() -> None:
    mcp.run()  # stdio


if __name__ == "__main__":
    main()
