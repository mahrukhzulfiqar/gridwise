from datetime import datetime, timedelta

import pytest

from gridwise.eds_client import DK_TZ, Co2Point, PricePoint
from gridwise.planner import merge, plan_charging

START = datetime(2026, 11, 14, 17, 0, tzinfo=DK_TZ)


def make_slots(prices, co2=None):
    pts = [PricePoint(START + timedelta(minutes=15 * i), p, 0.0) for i, p in enumerate(prices)]
    co2_pts = [Co2Point(START + timedelta(minutes=15 * i), c) for i, c in enumerate(co2 or [])]
    return merge(pts, co2_pts)


def test_picks_cheapest_contiguous_window():
    # 8 slots (2 h). Cheapest 1 h block is slots 4-7.
    slots = make_slots([2.0, 2.0, 1.5, 1.5, 0.5, 0.4, 0.6, 0.5])
    plan = plan_charging(
        slots, kwh=11, charger_kw=11, earliest=START, latest=START + timedelta(hours=2), priority="cheapest"
    )
    assert plan.duration_minutes == 60
    assert plan.recommended.start == START + timedelta(hours=1)
    assert plan.recommended.est_spot_cost_dkk == pytest.approx(0.5 * 11)
    assert plan.baseline.start == START


def test_greenest_can_differ_from_cheapest():
    prices = [0.5, 0.5, 0.5, 0.5, 1.0, 1.0, 1.0, 1.0]
    co2 = [200, 200, 200, 200, 50, 50, 50, 50]
    slots = make_slots(prices, co2)
    end = START + timedelta(hours=2)
    cheap = plan_charging(slots, 11, 11, START, end, "cheapest")
    green = plan_charging(slots, 11, 11, START, end, "greenest")
    assert cheap.recommended.start == START
    assert green.recommended.start == START + timedelta(hours=1)
    assert green.to_dict()["co2_saving_vs_baseline_kg"] == pytest.approx((200 - 50) * 11 / 1000)


def test_falls_back_to_price_when_no_co2():
    slots = make_slots([1.0, 1.0, 0.2, 0.2])
    plan = plan_charging(slots, 5.5, 11, START, START + timedelta(hours=1), "greenest")
    assert plan.recommended.start == START + timedelta(minutes=30)
    assert any("price-only" in n for n in plan.notes)


def test_respects_ready_by_time():
    slots = make_slots([1.0, 1.0, 1.0, 1.0, 0.1, 0.1, 0.1, 0.1])
    plan = plan_charging(slots, 11, 11, START, START + timedelta(hours=1), "cheapest")
    assert plan.recommended.end <= START + timedelta(hours=1)


def test_not_enough_time_raises():
    slots = make_slots([1.0] * 4)
    with pytest.raises(ValueError, match="needs 2 h"):
        plan_charging(slots, 22, 11, START, START + timedelta(hours=1))


def test_rounds_partial_slot_up():
    slots = make_slots([1.0] * 8)
    plan = plan_charging(slots, kwh=12, charger_kw=11, earliest=START, latest=START + timedelta(hours=2))
    assert plan.duration_minutes == 75


def test_skips_windows_with_gaps():
    pts = [PricePoint(START + timedelta(minutes=15 * i), 0.1 if i in (1, 3) else 1.0, 0) for i in (0, 1, 3, 4)]
    plan = plan_charging(merge(pts, []), 5.5, 11, START, START + timedelta(hours=2), "cheapest")
    # slots 1 and 3 are cheap but not adjacent (slot 2 missing), so no window may span the gap
    assert plan.recommended.end - plan.recommended.start == timedelta(minutes=30)
    assert plan.recommended.start != START + timedelta(minutes=15)


def test_invalid_inputs():
    slots = make_slots([1.0] * 4)
    with pytest.raises(ValueError):
        plan_charging(slots, 0, 11, START, START + timedelta(hours=1))
    with pytest.raises(ValueError):
        plan_charging(slots, 5, 11, START, START + timedelta(hours=1), "fastest")  # type: ignore[arg-type]
