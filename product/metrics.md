# Success metrics

GridWise is a portfolio product, so usage numbers will be small. The point of this page is to show which metrics I would run it on and how each would be measured.

## North star
**Saving per charging session versus plugging in and charging immediately**, in DKK and kg CO2.
Why: it measures the value the user actually gets, not engagement. It is already computed for every plan (`spot_saving_vs_baseline_dkk`, `co2_saving_vs_baseline_kg`).

## Supporting metrics

| Area | Metric | Target (v0.x) | How measured |
|---|---|---|---|
| Value | Median spot saving per 40 kWh session | > 15 DKK | Planner output, logged per request |
| Value | Median CO2 saving per 40 kWh session | > 1 kg | Planner output |
| Trust | Answers where every number comes from a tool call | 100% | Agent trace: numbers in reply vs tool results (eval set) |
| Trust | Correct tool chosen for the question | ≥ 95% | Eval set of labelled questions (roadmap: Next) |
| Quality | "Not published yet" handled without guessing | 100% | Eval questions asked before 13:00 |
| Experience | p95 time to answer in chat | < 8 s | App timing log |
| Experience | Chat questions needing a follow-up to clarify | < 20% | Conversation review |
| Adoption | Repeat use within 7 days | Track only | Streamlit analytics |

## Guardrails
- Zero answers that quote a price without saying it is spot only.
- Energi Data Service rate limit (about 50 calls per 10 s per IP) never hit: cache responses for 15 minutes in the app.

## What I would not optimise
Number of chat messages or time in app. A good answer is short and ends the conversation.
