import json
from datetime import date

import httpx
import pytest

from gridwise import eds_client as eds


def mock_client(records, captured=None, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(request)
        return httpx.Response(status, json={"total": len(records), "records": records})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_prices_parsed_converted_and_filtered_to_danish_day():
    records = [
        # 22:45 UTC on 13 Nov = 23:45 DK on 13 Nov -> outside the day, dropped
        {"TimeUTC": "2026-11-13T22:45:00", "PriceArea": "DK2", "DayAheadPriceDKK": 999.0, "DayAheadPriceEUR": 134.0},
        # 23:00 UTC on 13 Nov = 00:00 DK on 14 Nov -> first slot of the day
        {"TimeUTC": "2026-11-13T23:00:00", "PriceArea": "DK2", "DayAheadPriceDKK": 512.5, "DayAheadPriceEUR": 68.7},
        {"TimeUTC": "2026-11-13T23:15:00", "PriceArea": "DK2", "DayAheadPriceDKK": None, "DayAheadPriceEUR": None},
    ]
    captured = []
    pts = eds.get_day_ahead_prices("dk2", date(2026, 11, 14), client=mock_client(records, captured))
    assert len(pts) == 1
    assert pts[0].start.hour == 0 and pts[0].start.day == 14
    assert pts[0].dkk_per_kwh == pytest.approx(0.5125)
    params = captured[0].url.params
    assert json.loads(params["filter"]) == {"PriceArea": ["DK2"]}
    assert params["timezone"] == "UTC"


def test_co2_averaged_to_quarter_hours():
    records = [
        {"Minutes5UTC": "2026-11-14T11:00:00", "CO2Emission": 100},
        {"Minutes5UTC": "2026-11-14T11:05:00", "CO2Emission": 110},
        {"Minutes5UTC": "2026-11-14T11:10:00", "CO2Emission": 120},
        {"Minutes5UTC": "2026-11-14T11:15:00", "CO2Emission": 50},
    ]
    pts = eds.get_co2_forecast("DK1", date(2026, 11, 14), client=mock_client(records))
    assert [p.g_per_kwh for p in pts] == [110.0, 50.0]
    assert pts[0].start.hour == 12  # 11:00 UTC = 12:00 CET


def test_dst_day_has_100_quarters():
    # 25 Oct 2026: clocks go back, the Danish day is 25 hours long
    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 10, 24, 22, 0, tzinfo=timezone.utc)  # 00:00 CEST
    records = [
        {"TimeUTC": (start + timedelta(minutes=15 * i)).replace(tzinfo=None).isoformat(), "DayAheadPriceDKK": 500.0}
        for i in range(100)
    ]
    pts = eds.get_day_ahead_prices("DK2", date(2026, 10, 25), client=mock_client(records))
    assert len(pts) == 100


def test_retries_after_429(monkeypatch):
    monkeypatch.setattr(eds.time, "sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json={"records": [{"TimeUTC": "2026-11-14T11:00:00", "DayAheadPriceDKK": 400.0}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    pts = eds.get_day_ahead_prices("DK2", date(2026, 11, 14), client=client)
    assert len(calls) == 2 and len(pts) == 1


def test_http_error_becomes_eds_error(monkeypatch):
    monkeypatch.setattr(eds.time, "sleep", lambda s: None)
    with pytest.raises(eds.EDSError, match="Try again later"):
        eds.get_day_ahead_prices("DK2", date(2026, 11, 14), client=mock_client([], status=503))


def test_unknown_area_rejected():
    with pytest.raises(ValueError):
        eds.get_day_ahead_prices("SE4", date(2026, 11, 14), client=mock_client([]))


def test_offline_mode_uses_sample(monkeypatch):
    monkeypatch.setenv("GRIDWISE_OFFLINE", "1")
    pts = eds.get_day_ahead_prices("DK1", date(2027, 1, 5))
    assert len(pts) == 96
    assert all(p.start.date() == date(2027, 1, 5) for p in pts)


def test_429_with_long_wait_fails_fast_with_message(monkeypatch):
    slept = []
    monkeypatch.setattr(eds.time, "sleep", slept.append)
    resp = httpx.Response(429, text='{"message": "Rate limit is exceeded. Try again in 55 seconds."}')
    client = httpx.Client(transport=httpx.MockTransport(lambda r: resp))
    with pytest.raises(eds.EDSError, match="about 55 seconds"):
        eds.get_day_ahead_prices("DK2", date(2026, 11, 14), client=client)
    assert slept == []


def test_one_call_covers_today_and_tomorrow(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "records": [
                    {"TimeUTC": "2026-11-14T11:00:00", "DayAheadPriceDKK": 400.0},
                    {"TimeUTC": "2026-11-15T11:00:00", "DayAheadPriceDKK": 300.0},
                ]
            },
        )

    eds._CACHE.clear()
    real_client = httpx.Client
    monkeypatch.setattr(eds.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler)))
    today = eds.get_day_ahead_prices("DK2", date(2026, 11, 14))
    tomorrow = eds.get_day_ahead_prices("DK2", date(2026, 11, 15))
    assert len(calls) == 1
    assert [p.dkk_per_kwh for p in today] == [0.4]
    assert [p.dkk_per_kwh for p in tomorrow] == [0.3]
    eds._CACHE.clear()
