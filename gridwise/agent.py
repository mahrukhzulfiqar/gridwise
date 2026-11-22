"""A small Claude agent that answers energy questions by calling the GridWise MCP server.

The agent discovers tools over MCP at runtime, so anything added to the server
is available to the agent without code changes here.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from anthropic import Anthropic
from mcp import Client, StdioServerParameters

from .eds_client import DK_TZ

DEFAULT_MODEL = os.getenv("GRIDWISE_MODEL", "claude-sonnet-5-5")
MAX_TOOL_ROUNDS = 6

SYSTEM_PROMPT = """You are GridWise, an assistant for households in Denmark who want to use \
electricity when it is cheap and green, for example to charge an EV.

Rules:
- Use the tools for every number. Never estimate prices or CO2 yourself.
- For "when should I charge" questions, call plan_ev_charging. If the user did not say how much \
energy, assume 40 kWh and an 11 kW home charger, and say you assumed it.
- Default price area is DK2 (Zealand, Copenhagen) unless the user mentions Jutland, Funen, Aarhus, \
Odense, Aalborg or DK1.
- Prices are spot prices only. Say this once, briefly.
- If prices are not published yet, explain when they usually are. Do not guess.
- Answer in the user's language (Danish or English). Lead with the answer: the time window, then \
cost and CO2 versus charging straight away. Keep it under 120 words. Use 24-hour times.
Current time in Denmark: {now}"""


@dataclass
class ToolCall:
    name: str
    arguments: dict
    result: str
    is_error: bool


@dataclass
class AgentReply:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


def server_params() -> StdioServerParameters:
    """Launch the GridWise MCP server as a subprocess over stdio."""
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "gridwise.server"],
        env={**os.environ},
        cwd=str(Path(__file__).resolve().parent.parent),
    )


async def _ask(question: str, history: list[dict], model: str, server) -> AgentReply:
    from datetime import datetime

    anthropic = Anthropic()
    calls: list[ToolCall] = []
    async with Client(server) as mcp_client:
        listed = await mcp_client.list_tools()
        tools = [
            {"name": t.name, "description": t.description or "", "input_schema": t.input_schema} for t in listed.tools
        ]
        messages = [*history, {"role": "user", "content": question}]
        system = SYSTEM_PROMPT.format(now=datetime.now(DK_TZ).strftime("%A %d %B %Y %H:%M"))

        for _ in range(MAX_TOOL_ROUNDS):
            resp = anthropic.messages.create(
                model=model, max_tokens=1024, system=system, tools=tools, messages=messages
            )
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason != "tool_use":
                text = "".join(b.text for b in resp.content if b.type == "text").strip()
                return AgentReply(text=text, tool_calls=calls)

            results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                out = await mcp_client.call_tool(block.name, block.input)
                text = "\n".join(c.text for c in out.content if getattr(c, "type", "") == "text")
                calls.append(ToolCall(block.name, dict(block.input), text, bool(out.is_error)))
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": text, "is_error": bool(out.is_error)}
                )
            messages.append({"role": "user", "content": results})

    return AgentReply(text="Sorry, I could not finish that within the tool-call limit.", tool_calls=calls)


def ask(question: str, history: list[dict] | None = None, model: str = DEFAULT_MODEL, server=None) -> AgentReply:
    """Synchronous entry point. ``server`` defaults to the stdio subprocess."""
    return asyncio.run(_ask(question, history or [], model, server or server_params()))


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "When is the cheapest and greenest time to charge my EV tonight in DK2?"
    reply = ask(q)
    for c in reply.tool_calls:
        print(f"[tool] {c.name}({json.dumps(c.arguments)})")
    print(reply.text)
