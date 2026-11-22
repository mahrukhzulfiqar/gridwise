# Decision log

Short records of decisions that shaped GridWise: the context, what I chose, and what I gave up.

---

### D1. Expose the data as an MCP server, not as functions inside the app
**Context:** The agent needs price, CO2 and planning tools. The simplest option is to define them directly in the agent code.
**Decision:** Put them behind an MCP server and have the agent discover them at runtime.
**Why:** The same tools then work in Claude Desktop, other MCP clients and future agents without rewriting. New tools appear in the agent with no agent changes.
**Trade-off:** One more process and a small amount of latency per question.

### D2. The model talks, the code calculates
**Context:** An LLM can read a price table and suggest a window, but it may get arithmetic or time zones wrong, and the answer cannot be tested.
**Decision:** All calculations happen in a deterministic planner. The model chooses the tool, fills in arguments and explains the result. The system prompt forbids estimating numbers, and the UI shows every tool call.
**Why:** Reproducible, unit-testable answers, and a user can check how the answer was made.
**Trade-off:** Less flexible for unusual questions; those need new tools.

### D3. Use DayAheadPrices at 15-minute resolution
**Context:** Most examples online use the `Elspotprices` dataset. It stopped at 30 September 2025, when the day-ahead market moved to 15-minute periods and Energinet introduced `DayAheadPrices`.
**Decision:** Use `DayAheadPrices` and keep 15-minute slots in the planner. Send hourly summaries to the model.
**Why:** 15-minute slots give better windows. Hourly summaries cut tokens about fourfold without losing what the model needs to explain the answer.
**Trade-off:** Window boundaries can fall on quarter hours, which is fine for chargers.

### D4. Use the CO2 forecast, not real-time CO2
**Context:** Energi Data Service has both real-time (`CO2Emis`) and forecast (`CO2EmisProg`) CO2 intensity.
**Decision:** Use the forecast.
**Why:** The user is deciding about the coming hours, so the forecast is the relevant signal.
**Trade-off:** Forecasts can be wrong; the plan is a recommendation, not a guarantee.

### D5. Ship with spot price only, and say so every time
**Context:** What a household pays includes grid tariff, electricity tax and VAT. Tariffs differ by grid company and peak 17:00 to 21:00.
**Decision:** v0.1 uses spot price only. Every answer and the UI state this. All-in price is first in Next.
**Why:** Getting a working, trusted loop out early matters more than completeness, as long as the limitation is visible. Tariffs mostly make evening charging look worse, so spot-only advice points the same way.
**Trade-off:** Savings shown are lower than the real bill difference near the tariff peak.

### D6. Recommend one continuous window
**Context:** The cheapest set of quarter hours might be spread across the night.
**Decision:** Recommend one continuous session.
**Why:** It matches how most people and chargers schedule charging, and it is easy to act on.
**Trade-off:** Leaves a small saving on the table in some nights.

### D7. A planner that works without the LLM
**Context:** Chat needs an API key, costs money per question and can fail.
**Decision:** The planner tab calls the same planner directly, with no LLM.
**Why:** Works for anyone who opens the demo, costs nothing, and is a fallback if the model API is down. It also proves the value is in the planner, not the chat wrapper.

### D8. State defaults instead of asking
**Context:** Users often ask "when should I charge?" without saying how much energy or which area.
**Decision:** Assume 40 kWh, 11 kW and DK2 (unless a West Denmark place is mentioned), and say so in the answer.
**Why:** One useful answer beats a round of clarifying questions; the user can correct the assumption.

### D9. "Balanced" is a normalised weighted score
**Context:** Price and CO2 have different units and ranges.
**Decision:** Min-max normalise both across candidate windows, then weight 50/50 for balanced.
**Why:** Simple, explainable and stable. The user can choose cheapest or greenest to override.
**Trade-off:** Relative, not absolute: a day with tiny CO2 variation still gives CO2 half the weight.

### D10. Design for the data provider's rate limits
**Context:** On the first live run, Energi Data Service answered HTTP 429 (too many requests). In 2026 Energinet introduced per-dataset rate limits on the API, and the planner was making one call per dataset per day: four calls for "today and tomorrow".
**Decision:** Fetch today and tomorrow in one call per dataset, cache results for 15 minutes, wait and retry when the API asks for a short pause, and otherwise tell the user how long to wait. Identify the app with its own User-Agent.
**Why:** Prices change once a day, so repeated calls add nothing. Respecting the provider's limits keeps the product working for every user and keeps us a good citizen of a free public service.
**Trade-off:** A CO2 forecast update can take up to 15 minutes to appear.
