"""End-to-end over MCP: an in-process client calls the real server tools on sample data."""

import json
from datetime import datetime

import pytest
from mcp import Client

from gridwise import server
from gridwise.eds_client import DK_TZ


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("GRIDWISE_OFFLINE", "1")
    monkeypatch.setattr(server, "_now", lambda: datetime(2026, 11, 14, 15, 0, tzinfo=DK_TZ))


async def call(name, args):
    async with Client(server.mcp) as client:
        res = await client.call_tool(name, args)
        assert not res.is_error, res.content[0].text
        return json.loads(res.content[0].text)


@pytest.mark.anyio
async def test_lists_three_tools():
    async with Client(server.mcp) as client:
        names = {t.name for t in (await client.list_tools()).tools}
    assert names == {"get_prices", "get_co2_forecast", "plan_ev_charging"}


@pytest.mark.anyio
async def test_get_prices_hourly_summary():
    out = await call("get_prices", {"area": "DK2", "day": "tomorrow"})
    assert out["published"] and out["date"] == "2026-11-15"
    assert len(out["hourly"]) == 24


@pytest.mark.anyio
async def test_plan_overnight_beats_charging_at_17():
    out = await call("plan_ev_charging", {"kwh": 40, "plug_in_time": "17:00", "ready_by": "07:00"})
    assert out["planned"]
    assert out["spot_saving_vs_baseline_dkk"] > 0
    assert out["recommended"]["start"] != out["baseline_charge_immediately"]["start"]


@pytest.mark.anyio
async def test_bad_time_is_reported_as_tool_error():
    async with Client(server.mcp) as client:
        res = await client.call_tool("plan_ev_charging", {"kwh": 40, "plug_in_time": "5pm"})
    assert res.is_error
