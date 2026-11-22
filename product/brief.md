# GridWise: one-page product brief

**Status:** v0.1 shipped · **Owner:** Mahrukh · **Last updated:** November 2026

## Problem
Since October 2025, Danish day-ahead electricity prices change every 15 minutes, and the CO2 intensity of the grid varies a lot through the day. An EV is the largest flexible load in most homes, yet most people plug in and charge at around 17:00, at the evening peak for both price and CO2. The data needed to do better is free and public (Energinet's Energi Data Service), but it is raw market data that households will not query themselves.

## Target user
**Primary:** a household in Denmark with an EV and a home charger (7 to 22 kW), who cares about cost and climate but will not study the electricity market.
**Secondary:** developers and energy companies who want Danish price and CO2 data as tools for their own AI agents (via MCP).

## Job to be done
*When I plug in my car in the evening, I want to know when to charge so it is ready in the morning, at the lowest cost and CO2, without doing any research.*

## Solution (v0.1)
- A chat assistant that answers in English or Danish, grounded in live Energinet data.
- A planner that finds the best continuous charging window between plug-in and ready-by, optimised for price, CO2 or both, and shows the saving compared with charging straight away.
- An MCP server, so the same capability works in Claude Desktop or any MCP-compatible agent.

## In scope
DK1 and DK2 · spot price and CO2 forecast · one continuous charging session · today and tomorrow.

## Out of scope (for now)
Grid tariffs and taxes (next) · controlling the charger · other appliances · user accounts · historical analytics.

## Key assumptions to test
1. Users trust a recommendation more when they see the "vs charging now" comparison.
2. A balanced price/CO2 default is preferred over pure cheapest.
3. Spot-only savings are large enough to change behaviour before tariffs are added.

## Risks and mitigations
| Risk | Mitigation |
|---|---|
| Model invents prices or times | All numbers come from tools; system prompt forbids estimates; tool calls are shown to the user |
| User reads spot price as their bill | Every answer and the UI state "spot only"; tariffs are top of the roadmap |
| Tomorrow's prices not yet published | Explicit "not published yet" state with expected time |
| Upstream data model changes (as with Elspotprices to DayAheadPrices) | Thin client layer, mocked API tests, sample data fallback |

## Success
See [metrics.md](metrics.md).
