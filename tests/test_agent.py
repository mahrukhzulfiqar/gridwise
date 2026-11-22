"""Agent loop test with a stubbed Claude: checks MCP tool discovery, dispatch and result passing."""

from datetime import datetime
from types import SimpleNamespace as NS

import pytest

from gridwise import agent, server
from gridwise.eds_client import DK_TZ


class FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            use = NS(type="tool_use", id="t1", name="plan_ev_charging", input={"kwh": 40, "area": "DK2"})
            return NS(stop_reason="tool_use", content=[use])
        return NS(stop_reason="end_turn", content=[NS(type="text", text="Charge 00:30 to 04:15.")])


@pytest.fixture
def fake_claude(monkeypatch):
    msgs = FakeMessages()
    monkeypatch.setattr(agent, "Anthropic", lambda: NS(messages=msgs))
    monkeypatch.setenv("GRIDWISE_OFFLINE", "1")
    monkeypatch.setattr(server, "_now", lambda: datetime(2026, 11, 14, 15, 0, tzinfo=DK_TZ))
    return msgs


def test_agent_calls_mcp_tool_and_returns_answer(fake_claude):
    reply = agent.ask("When should I charge tonight?", server=server.mcp)
    assert reply.text == "Charge 00:30 to 04:15."
    assert [c.name for c in reply.tool_calls] == ["plan_ev_charging"]
    assert not reply.tool_calls[0].is_error
    # tools were discovered over MCP and offered to the model
    offered = {t["name"] for t in fake_claude.calls[0]["tools"]}
    assert "plan_ev_charging" in offered
    # the tool result was sent back to the model
    # messages: [user question, assistant tool_use, user tool_result, ...]
    tool_result = fake_claude.calls[1]["messages"][2]["content"][0]
    assert tool_result["type"] == "tool_result" and '"planned": true' in tool_result["content"]
