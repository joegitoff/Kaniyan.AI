"""
app.py - Kaniyan.AI Streamlit dashboard.   Run with:  streamlit run app.py

Python concepts: Streamlit widgets, caching, session state, exception handling,
DataFrames, f-strings, modular imports.
"""
from __future__ import annotations

import copy
from datetime import timezone

import pandas as pd
import streamlit as st

import alert_engine
import charts
import config
import data_service as ds
import llm_service
import recommendations
import sample_data
from config import Level

st.set_page_config(page_title="Kaniyan.AI", page_icon="🛡️", layout="wide")

LEVEL_ICON = {Level.INFO: "🔵", Level.CAUTION: "🟠", Level.HIGH: "🔴"}


# ------------------------------------------------------------------ cached API --
@st.cache_data(ttl=600, show_spinner=False)
def cached_search(query: str):
    return ds.search_locations(query, count=5)


@st.cache_data(ttl=600, show_spinner=False)
def cached_weather(location: ds.Location):
    return ds.fetch_weather(location)


@st.cache_data(ttl=600, show_spinner=False)
def cached_air(location: ds.Location):
    return ds.fetch_air_quality(location)


def fmt(value, unit="", digits=1):
    """Format a number or show 'n/a' for missing values."""
    if alert_engine.is_missing(value):
        return "n/a"
    return f"{float(value):.{digits}f}{unit}"


# --------------------------------------------------------------------- sidebar --
st.sidebar.title("🛡️ Kaniyan.AI")
demo_mode = st.sidebar.toggle("Demo mode (SAMPLE data, no internet)", value=False,
                              help="Uses invented sample data for offline demonstrations. A banner is always shown.")

weather = air = None
location = None
errors = []

if demo_mode:
    location = sample_data.SAMPLE_LOCATION
else:
    st.sidebar.subheader("Location")
    quick = st.sidebar.selectbox("Quick pick", config.QUICK_CITIES, index=0)
    typed = st.sidebar.text_input("...or type any city", value="", placeholder="e.g. Kumbakonam")
    query = typed.strip() or quick
    try:
        matches = cached_search(query)
        labels = [m.label for m in matches]
        chosen = st.sidebar.selectbox("Matching places", labels, index=0)
        location = matches[labels.index(chosen)]
    except ds.DataServiceError as exc:
        st.sidebar.error(str(exc))

with st.sidebar.expander("Alert thresholds (illustrative)"):
    st.caption(config.THRESHOLD_NOTE)
    thresholds = copy.deepcopy(config.DEFAULT_THRESHOLDS)
    for key, label in config.THRESHOLD_LABELS.items():
        st.markdown(f"**{label}**")
        cols = st.columns(3)
        for col, level_key in zip(cols, ("info", "caution", "high")):
            thresholds[key][level_key] = col.number_input(
                level_key.capitalize(), value=float(thresholds[key][level_key]),
                key=f"{key}_{level_key}", step=1.0)

use_llm = st.sidebar.checkbox("Use Groq AI explanation (needs API key)", value=False)
if llm_service.is_configured():
    st.sidebar.caption("✅ Groq API key found. The AI chat tab is active.")
else:
    st.sidebar.caption("ℹ️ No Groq key found - AI features use the rule-based fallback. "
                       "The app works fully without an LLM.")

# ---------------------------------------------------------------------- header --
st.title("🛡️ Kaniyan.AI")
st.caption("Location-based environmental risk alerts: weather, rainfall, heat, wind and air quality "
           "with transparent, rule-based warnings and practical precautions.")

if location is None:
    st.warning("Choose a valid location in the sidebar to begin (or switch on Demo mode).")
    st.stop()

# ------------------------------------------------------------------ load data --
if demo_mode:
    weather = sample_data.load_sample_weather()
    air = sample_data.load_sample_air_quality()
    st.error("⚠️ SAMPLE DATA - these numbers are invented for demonstration. They are NOT live "
             "observations or forecasts.")
else:
    with st.spinner("Fetching weather and air-quality data..."):
        try:
            weather = cached_weather(location)
        except ds.DataServiceError as exc:
            st.error(f"Weather data could not be retrieved: {exc}")
            st.info("Tip: check your internet connection, wait a minute if you hit a rate limit, "
                    "or switch on Demo mode in the sidebar to show the interface with sample data.")
            st.stop()
        try:
            air = cached_air(location)
        except ds.DataServiceError as exc:
            errors.append(f"Air-quality data could not be retrieved: {exc}")

for message in errors:
    st.warning(message)

try:
    alerts = alert_engine.evaluate_alerts(weather, air, thresholds)
except ValueError as exc:
    st.error(f"Invalid thresholds: {exc} Using defaults instead.")
    alerts = alert_engine.evaluate_alerts(weather, air, config.DEFAULT_THRESHOLDS)

st.subheader(f"📍 {location.label}")
st.caption(f"Coordinates: {location.latitude:.2f}, {location.longitude:.2f} · Time zone: {weather.timezone}")

tab_overview, tab_forecast, tab_air, tab_alerts, tab_chat, tab_about = st.tabs(
    ["Overview", "Forecast", "Air quality", "Alerts & precautions", "Kaniyan.AI Chat", "Sources & notes"])

# -------------------------------------------------------------------- overview --
with tab_overview:
    cur = weather.current
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Temperature", fmt(cur.get("temperature_2m"), " °C"))
    c2.metric("Feels like", fmt(cur.get("apparent_temperature"), " °C"))
    c3.metric("Humidity", fmt(cur.get("relative_humidity_2m"), " %", 0))
    c4.metric("Wind", fmt(cur.get("wind_speed_10m"), " km/h"))
    c5.metric("Condition", cur.get("weather_text", "n/a"))

    worst = alert_engine.highest_level(alerts)
    if worst is None:
        st.success("No configured rule is triggered in the forecast period.")
    else:
        st.markdown(f"**Highest alert level in forecast:** {LEVEL_ICON[worst]} {worst.label} "
                    f"({len(alerts)} alert(s)). See the *Alerts & precautions* tab.")
    st.caption(f"Model time of current values: {cur.get('time', 'n/a')} (local) · "
               f"Fetched: {weather.fetched_at.astimezone(timezone.utc):%Y-%m-%d %H:%M} UTC")

    st.markdown("#### Explanation")
    signature = (location.label, tuple((a.key, a.when, a.value) for a in alerts), weather.is_sample)
    if use_llm:
        if st.button("Generate AI explanation"):
            st.session_state["llm_result"] = (signature,
                llm_service.explain(location.label, weather, air, alerts, use_llm=True))
        saved = st.session_state.get("llm_result")
        explanation = saved[1] if saved and saved[0] == signature else None
    else:
        explanation = None
    if explanation is None:   # default: ordinary Python explanation (free, instant, no key)
        explanation = llm_service.explain(location.label, weather, air, alerts, use_llm=False)
        if use_llm:
            explanation.note = "Press the button above to request an LLM explanation."
    st.write(explanation.text)
    st.caption(f"Explanation source: {explanation.source}" + (f" - {explanation.note}" if explanation.note else ""))

# -------------------------------------------------------------------- forecast --
with tab_forecast:
    daily = weather.daily
    table = pd.DataFrame({
        "Date": daily["date"].dt.strftime("%a %d %b"),
        "Condition": daily.get("weather_text"),
        "Max °C": daily.get("temperature_2m_max"),
        "Min °C": daily.get("temperature_2m_min"),
        "Rain mm": daily.get("precipitation_sum"),
        "Rain prob. max %": daily.get("precipitation_probability_max"),
        "Max gust km/h": daily.get("wind_gusts_10m_max"),
        "UV max": daily.get("uv_index_max"),
    })
    st.dataframe(table, hide_index=True)
    st.caption("Blank cells mean the data service did not provide that value.")
    left, right = st.columns(2)
    left.plotly_chart(charts.temperature_chart(daily, thresholds["temp_max_c"]["caution"]))
    right.plotly_chart(charts.rainfall_chart(daily, thresholds["rain_daily_mm"]["caution"]))
    st.plotly_chart(charts.wind_chart(daily, thresholds["wind_gust_kmh"]["caution"]))

# ----------------------------------------------------------------- air quality --
with tab_air:
    if air is None:
        st.warning("Air-quality data is unavailable right now. Weather features still work.")
    else:
        aq = air.current
        a1, a2, a3, a4 = st.columns(4)
        a1.metric("US AQI (model)", fmt(aq.get("us_aqi"), "", 0), ds.aqi_category_us(aq.get("us_aqi")))
        a2.metric("PM2.5 µg/m³", fmt(aq.get("pm2_5")))
        a3.metric("PM10 µg/m³", fmt(aq.get("pm10")))
        a4.metric("Ozone µg/m³", fmt(aq.get("ozone")))
        st.info("Which index is this? **US AQI** (EPA bands) as calculated by the Open-Meteo/CAMS "
                "**model**. It is not the Indian CPCB National AQI and not a ground-station reading. "
                "European AQI (shown below as a number only) uses a different scale - the two must not be compared.")
        eu = aq.get("european_aqi")
        st.caption(f"European AQI (different scale, model): {fmt(eu, '', 0)} · "
                   f"NO₂ {fmt(aq.get('nitrogen_dioxide'))} · SO₂ {fmt(aq.get('sulphur_dioxide'))} · "
                   f"CO {fmt(aq.get('carbon_monoxide'), '', 0)} (all µg/m³)")
        t = thresholds["us_aqi"]
        st.plotly_chart(charts.aqi_chart(air.hourly, t["info"], t["caution"], t["high"]))
        st.plotly_chart(charts.pm_chart(air.hourly))
        st.caption(f"Model values at: {aq.get('time', 'n/a')} (local) · "
                   f"Fetched: {air.fetched_at.astimezone(timezone.utc):%Y-%m-%d %H:%M} UTC")

# ---------------------------------------------------------------------- alerts --
with tab_alerts:
    st.info("These are **experimental, app-generated alerts** from simple threshold rules. "
            "They are not official warnings. " + alert_engine.RAIN_NOTE)
    if not alerts:
        st.success("No rule was triggered.")
    for a in alerts:
        with st.expander(f"{LEVEL_ICON[a.level]} {a.level.label} · {a.variable} · {a.when}",
                         expanded=a.level == Level.HIGH):
            st.markdown(f"**Location:** {a.location}  \n"
                        f"**Value:** {a.value:g} {a.unit}  \n"
                        f"**Rule that triggered:** {a.rule}  \n"
                        f"**Why:** {a.explanation}")
            st.markdown("**Precautions:**\n" + "\n".join(f"- {tip}" for tip in a.advice))
            st.caption(f"Source: {a.source} · Generated: {a.generated_at} · Official warning: No")
    st.markdown("#### Combined practical recommendations")
    for tip in recommendations.summarise_advice(alerts):
        st.markdown(f"- {tip}")
    with st.expander("What do the levels mean?"):
        for level, text in config.LEVEL_DEFINITIONS.items():
            st.markdown(f"**{level.label}** - {text}")
        st.caption(config.THRESHOLD_NOTE)
    if alerts:
        df = pd.DataFrame([a.to_dict() for a in alerts])[["level", "variable", "value", "unit", "when", "rule"]]
        st.download_button("Download alerts as CSV", df.to_csv(index=False), "kaniyan_alerts.csv", "text/csv")

# ---------------------------------------------------------------------- AI chat --
with tab_chat:
    st.subheader("💬 Ask Kaniyan.AI")
    st.write("Ask about the displayed weather, air quality, current alerts, or practical precautions.")
    st.caption("AI answers use the data shown in this dashboard. They are informational, not official warnings.")
    if "kaniyan_chat_history" not in st.session_state:
        st.session_state["kaniyan_chat_history"] = []
    # Old answers refer to the previous place's data, so start fresh when the place changes.
    if st.session_state.get("kaniyan_chat_location") != location.label:
        st.session_state["kaniyan_chat_history"] = []
        st.session_state["kaniyan_chat_location"] = location.label
    if not llm_service.is_configured():
        st.info("No GROQ_API_KEY found, so replies will be the rule-based summary. "
                "See the README for the 2-minute Groq setup.")
    chat_history = st.session_state["kaniyan_chat_history"]
    for message in chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    question = st.chat_input("e.g. Why is this alert shown, and what should I do?")
    if question:
        st.session_state["kaniyan_chat_history"].append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Preparing a simple answer..."):
                previous = st.session_state["kaniyan_chat_history"][:-1]
                result = llm_service.chat_answer(
                    question, location.label, weather, air, alerts, history=previous)
            st.markdown(result.text)
            st.caption(f"Answer source: {result.source}" + (f" · {result.note}" if result.note else ""))
        st.session_state["kaniyan_chat_history"].append({"role": "assistant", "content": result.text})
    if st.button("Clear chat", key="clear_kaniyan_chat"):
        st.session_state["kaniyan_chat_history"] = []
        st.rerun()

# ----------------------------------------------------------------------- about --
with tab_about:
    st.markdown("#### Data sources and timestamps")
    st.markdown(f"- **Weather:** {weather.source}  \n  Fetched: {weather.fetched_at:%Y-%m-%d %H:%M} UTC")
    if air is not None:
        st.markdown(f"- **Air quality:** {air.source}  \n  Fetched: {air.fetched_at:%Y-%m-%d %H:%M} UTC")
    st.markdown("- **Geocoding:** Open-Meteo Geocoding API (GeoNames)")
    st.caption(config.ATTRIBUTION)
    st.warning(recommendations.GENERAL_DISCLAIMER)
    st.markdown("**Official sources to check for real decisions:** India Meteorological Department "
                "(mausam.imd.gov.in), CPCB AQI bulletins (cpcb.nic.in), and your state disaster "
                "management authority.")
