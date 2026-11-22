# Roadmap

## Now (v0.1, shipped)
- MCP server with three tools: prices, CO2 forecast, EV charging plan
- Claude agent that discovers tools over MCP and shows its tool calls
- Streamlit app: chat plus a planner that works without an LLM
- 15-minute prices (DayAheadPrices) and CO2 forecast for DK1 and DK2
- Test suite and CI; offline mode with sample data
- Live demo on Streamlit Community Cloud (no sign-up, planner works without AI)
- Rate-limit-aware data access after Energinet introduced per-dataset limits

## Next
1. **All-in price.** Add grid tariffs per grid company (Radius, Cerius, N1 and others) from the `DatahubPricelist` dataset, plus electricity tax and VAT. This changes recommendations near the 17:00 to 21:00 tariff peak and makes savings match the bill.
2. **Eval set.** 25 labelled questions (English and Danish, DK1 and DK2, before and after price publication) with the expected tool and arguments. Run in CI against a stubbed API.
3. **User interviews** with 5 EV owners: how they decide when to charge today, and what would make them trust a recommendation. Findings go in `product/discovery.md`.
4. **Usage logging** for the metrics in [metrics.md](metrics.md), without storing personal data.

## Later
- Control the charger: schedule a session through charger APIs (for example Easee or Zaptec) after the user confirms
- "Prices are out" notification when tomorrow's prices are published, with tonight's best window
- Other flexible loads: heat pump, dishwasher, washing machine
- Home Assistant integration
- Split charging sessions when the car has a long plug-in window

## Not planned
- Price forecasting beyond published day-ahead prices
- Trading or retail electricity contracts
