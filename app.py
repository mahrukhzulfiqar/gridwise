"""GridWise Streamlit app: chat with the agent, or use the planner directly."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from gridwise import eds_client as eds
from gridwise.planner import merge, plan_charging


def _delta(diff: float, fmt: str, threshold: float = 0.5) -> str | None:
    """Metric delta text, or None (no arrow) when the difference rounds to zero."""
    return fmt.format(diff) if abs(diff) >= threshold else None


st.set_page_config(page_title="GridWise", page_icon="⚡", layout="centered")

# Streamlit Community Cloud secrets -> environment, so the MCP subprocess sees them too
for key in ("ANTHROPIC_API_KEY", "GRIDWISE_MODEL", "GRIDWISE_OFFLINE"):
    try:
        if key in st.secrets and key not in os.environ:
            os.environ[key] = str(st.secrets[key])
    except FileNotFoundError:
        pass

st.title("⚡ GridWise")
st.caption(
    "When is electricity cheapest and greenest in Denmark? "
    "Live data from Energinet's Energi Data Service. Spot prices only, excl. tariffs, taxes and VAT."
)
if os.getenv("GRIDWISE_OFFLINE"):
    st.warning("Offline demo mode: using bundled sample data, not live prices.")

area = st.sidebar.radio("Price area", ["DK2", "DK1"], format_func=lambda a: f"{a}: {eds.PRICE_AREAS[a]}")

tab_chat, tab_plan = st.tabs(["Ask GridWise", "Charging planner"])

# ---------------------------------------------------------------- chat
with tab_chat:
    if not os.getenv("ANTHROPIC_API_KEY"):
        st.info(
            "Add ANTHROPIC_API_KEY to your environment or Streamlit secrets to enable chat. "
            "The planner tab works without it."
        )
    else:
        from gridwise.agent import ask

        st.session_state.setdefault("history", [])
        st.session_state.setdefault("display", [])
        for role, text, calls in st.session_state.display:
            with st.chat_message(role):
                st.markdown(text)
                if calls:
                    with st.expander(f"How I got this ({len(calls)} tool call{'s' if len(calls) > 1 else ''})"):
                        for c in calls:
                            st.code(f"{c.name}({json.dumps(c.arguments)})", language="python")

        examples = [
            f"Cheapest and greenest time to charge 40 kWh tonight in {area}? I leave at 07:30.",
            f"Hvornår er strømmen billigst i morgen i {area}?",
        ]
        cols = st.columns(len(examples))
        clicked = next(
            (ex for col, ex in zip(cols, examples, strict=True) if col.button(ex, use_container_width=True)), None
        )
        prompt = st.chat_input("Ask about prices, CO2 or when to charge") or clicked

        if prompt:
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Checking Energi Data Service..."):
                    try:
                        reply = ask(prompt, history=st.session_state.history)
                        text, calls = reply.text, reply.tool_calls
                    except Exception as exc:  # noqa: BLE001  show a useful message, not a stack trace
                        text, calls = f"Something went wrong: {exc}", []
                st.markdown(text)
            st.session_state.history += [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": text},
            ]
            st.session_state.display += [("user", prompt, []), ("assistant", text, calls)]
            st.rerun()

# ---------------------------------------------------------------- planner (no LLM)
with tab_plan:
    c1, c2 = st.columns(2)
    kwh = c1.number_input("Energy to add (kWh)", 1.0, 150.0, 40.0, step=5.0)
    charger_kw = c2.selectbox("Charger", [3.7, 7.4, 11.0, 22.0], index=2, format_func=lambda k: f"{k} kW")
    c3, c4, c5 = st.columns(3)
    plug_in = c3.time_input("Plug in", time(17, 0), step=900)
    ready_by = c4.time_input("Ready by", time(7, 0), step=900)
    priority = c5.selectbox("Optimise for", ["balanced", "cheapest", "greenest"])

    now = datetime.now(eds.DK_TZ)
    earliest = datetime.combine(now.date(), plug_in, tzinfo=eds.DK_TZ)
    latest = datetime.combine(now.date(), ready_by, tzinfo=eds.DK_TZ)
    if latest <= earliest:
        latest += timedelta(days=1)
    earliest = max(earliest, now.replace(second=0, microsecond=0) + timedelta(minutes=15 - now.minute % 15))

    @st.cache_data(ttl=900, show_spinner="Fetching prices and CO2 forecast...")
    def load(area_: str, days: tuple[date, ...]):
        prices, co2 = [], []
        for d in days:
            prices += eds.get_day_ahead_prices(area_, d)
            co2 += eds.get_co2_forecast(area_, d)
        return prices, co2

    try:
        prices, co2 = load(area, (now.date(), now.date() + timedelta(days=1)))
    except eds.EDSError as exc:
        st.error(f"Could not reach Energi Data Service: {exc}")
        st.stop()

    try:
        plan = plan_charging(merge(prices, co2), kwh, charger_kw, earliest, latest, priority)
    except ValueError as exc:
        st.warning(f"{exc} Tomorrow's prices are usually published around 13:00.")
    else:
        rec, base = plan.recommended, plan.baseline
        published_until = max(p.start for p in prices) + timedelta(minutes=15)
        if published_until < latest:
            st.warning(
                f"Prices are only published until {published_until:%a %H:%M}, so this plan ignores the hours "
                f"after that. Tomorrow's prices usually come out around 13:00. Check again then: "
                f"overnight is often cheaper."
            )
        st.subheader(f"Charge {rec.start:%a %H:%M} to {rec.end:%H:%M}")
        m1, m2, m3 = st.columns(3)
        m1.metric(
            "Avg spot price",
            f"{rec.avg_dkk_per_kwh:.2f} kr/kWh",
            _delta(rec.avg_dkk_per_kwh - base.avg_dkk_per_kwh, "{:+.2f} vs now", 0.005),
            delta_color="inverse",
        )
        if rec.avg_co2_g_per_kwh is not None and base.avg_co2_g_per_kwh is not None:
            m2.metric(
                "Avg CO2",
                f"{rec.avg_co2_g_per_kwh:.0f} g/kWh",
                _delta(rec.avg_co2_g_per_kwh - base.avg_co2_g_per_kwh, "{:+.0f} vs now"),
                delta_color="inverse",
            )
        m3.metric(
            "Spot cost",
            f"{rec.est_spot_cost_dkk:.0f} kr",
            _delta(rec.est_spot_cost_dkk - base.est_spot_cost_dkk, "{:+.0f} kr vs now"),
            delta_color="inverse",
        )
        for note in plan.notes:
            st.caption(note)

    if prices:
        df = pd.DataFrame(
            {"time": [p.start for p in prices], "Spot price (kr/kWh)": [p.dkk_per_kwh for p in prices]}
        ).set_index("time")
        if co2:
            df = df.join(
                pd.DataFrame({"time": [c.start for c in co2], "CO2 (g/kWh)": [c.g_per_kwh for c in co2]}).set_index(
                    "time"
                )
            )
        df.index = df.index.tz_localize(None)
        st.line_chart(df[["Spot price (kr/kWh)"]], height=200)
        if "CO2 (g/kWh)" in df:
            st.line_chart(df[["CO2 (g/kWh)"]], height=200, color="#2e7d32")

st.sidebar.markdown("---")
st.sidebar.caption("Data: Energinet, Energi Data Service (CC BY 4.0). Not endorsed by Energinet.")
st.sidebar.caption("[Source on GitHub](https://github.com/mahrukhzulfiqar/gridwise)")
