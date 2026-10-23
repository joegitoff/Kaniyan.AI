"""Optional Groq-powered plain-English explanations and chat for Kaniyan.AI.

The rule-based alert_engine remains the source of alert decisions. The LLM only
explains the already-computed data and answers questions using that context.
Without a Groq key or when the service is unavailable, safe Python fallbacks work.
"""
from __future__ import annotations
import json
import os
import re
from dataclasses import dataclass

try:  # optional: lets a local .env file supply GROQ_API_KEY
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# llama-3.3-70b-versatile was retired by Groq on 16 Aug 2026; this is its recommended replacement.
# Override without editing code: set KANIYAN_LLM_MODEL (env var or Streamlit secret).
DEFAULT_MODEL = "openai/gpt-oss-120b"
SYSTEM_PROMPT = (
    "You are Kaniyan.AI's environmental information assistant. Answer in simple English. "
    "ALWAYS start with a direct one-sentence answer to the question (e.g. 'Yes, rain is likely "
    "today: 70% chance, about 12 mm.'), then give 2-4 short, practical points. "
    "Use the supplied data and quote the actual numbers: current_weather, today and the "
    "daily_forecast (rain_mm, rain_chance_max_percent, temps, gusts, UV), next_24h_rain, "
    "air quality and alerts. 'rain_chance_max_percent' is the highest hourly chance of rain "
    "that day. Do not say data is missing if it is in the context; only say a value is "
    "unavailable when it is null or absent. Never invent numbers, forecasts, or official "
    "warnings. Kaniyan.AI alerts are experimental app-generated threshold alerts, not official "
    "warnings. Never guarantee safety or predict street-level flooding. Mention official IMD/"
    "CPCB/local disaster-management updates only briefly, and only when conditions are severe "
    "or the user asks about official warnings. If the data is marked sample/demo, say so."
)

@dataclass
class Explanation:
    text: str
    source: str
    note: str = ""


def _get_api_key() -> str:
    """Read key from environment first, then Streamlit secrets; never log it."""
    key = os.getenv("GROQ_API_KEY", "").strip()
    if key:
        return key
    try:
        import streamlit as st
        return str(st.secrets.get("GROQ_API_KEY", "")).strip()
    except Exception:
        return ""


def is_configured() -> bool:
    """True when a Groq API key is available (used by the UI to show status)."""
    return bool(_get_api_key())


def _get_model() -> str:
    """Model name from env, then Streamlit secrets, then the default."""
    name = (os.getenv("KANIYAN_LLM_MODEL") or os.getenv("GEOSHIELD_LLM_MODEL") or "").strip()  # old name still works
    if name:
        return name
    try:
        import streamlit as st
        name = str(st.secrets.get("KANIYAN_LLM_MODEL", "")).strip()
    except Exception:
        name = ""
    return name or DEFAULT_MODEL


def _number(v):
    try:
        f = float(v)
        return None if f != f else round(f, 1)
    except (TypeError, ValueError):
        return None


def _daily_rows(weather, limit=7):
    """Compact per-day forecast rows (today first) for the LLM context."""
    rows = []
    daily = getattr(weather, "daily", None)
    if daily is None or getattr(daily, "empty", True):
        return rows
    for i, r in daily.head(limit).iterrows():
        rows.append({
            "date": r["date"].strftime("%a %d %b") + (" (today)" if i == 0 else ""),
            "condition": r.get("weather_text"),
            "max_c": _number(r.get("temperature_2m_max")),
            "min_c": _number(r.get("temperature_2m_min")),
            "feels_like_max_c": _number(r.get("apparent_temperature_max")),
            "rain_mm": _number(r.get("precipitation_sum")),
            "rain_chance_max_percent": _number(r.get("precipitation_probability_max")),
            "wind_gust_max_kmh": _number(r.get("wind_gusts_10m_max")),
            "uv_max": _number(r.get("uv_index_max")),
        })
    return rows


def _next_24h_rain(weather, cur):
    """Summarise hourly rain for the next 24 hours from the current model time."""
    hourly = getattr(weather, "hourly", None)
    if hourly is None or getattr(hourly, "empty", True) or "precipitation" not in hourly.columns:
        return None
    try:
        import pandas as pd
        now = pd.to_datetime(cur.get("time"), errors="coerce")
        if pd.isna(now):
            now = hourly["time"].iloc[0]
        win = hourly[(hourly["time"] >= now.floor("h")) & (hourly["time"] < now.floor("h") + pd.Timedelta(hours=24))]
        if win.empty:
            return None
        prob = win["precipitation_probability"] if "precipitation_probability" in win.columns else None
        wet = win[win["precipitation"] >= 0.1]
        return {
            "total_rain_mm": _number(win["precipitation"].sum()),
            "max_hourly_rain_chance_percent": _number(prob.max()) if prob is not None else None,
            "hours_with_rain": int(len(wet)),
            "first_rain_hour": wet["time"].iloc[0].strftime("%a %H:%M") if len(wet) else None,
        }
    except Exception:
        return None


def build_payload(location_label, weather, air, alerts) -> dict:
    cur = weather.current if weather is not None else {}
    aq = air.current if air is not None else {}
    return {
        "location": location_label,
        "current_local_time": cur.get("time"),
        "data_is_sample_demo": bool(getattr(weather, "is_sample", False)),
        "current_weather": {
            "temperature_c": _number(cur.get("temperature_2m")),
            "feels_like_c": _number(cur.get("apparent_temperature")),
            "humidity_percent": _number(cur.get("relative_humidity_2m")),
            "wind_speed_kmh": _number(cur.get("wind_speed_10m")),
            "wind_gust_kmh": _number(cur.get("wind_gusts_10m")),
            "rain_now_mm": _number(cur.get("precipitation")),
            "condition": cur.get("weather_text"),
        },
        "next_24h_rain": _next_24h_rain(weather, cur) if weather is not None else None,
        "daily_forecast": _daily_rows(weather),
        "current_air_quality": {
            "us_aqi_model": _number(aq.get("us_aqi")),
            "pm2_5_ug_m3": _number(aq.get("pm2_5")),
            "pm10_ug_m3": _number(aq.get("pm10")),
        } if air is not None else "Unavailable",
        "alerts": [
            {"variable": a.variable, "value": a.value, "unit": a.unit,
             "rule": a.rule, "when": a.when, "level": a.level.label,
             "advice": list(a.advice)} for a in alerts
        ],
    }


def fallback_explanation(location_label, alerts, is_sample=False) -> str:
    prefix = "[SAMPLE DATA] " if is_sample else ""
    if not alerts:
        return (f"{prefix}For {location_label}, no configured alert rule was triggered "
                "in the forecast checked by this app. This does not guarantee that all "
                "conditions are safe. These are app-generated checks, not official warnings.")
    lines = [f"{prefix}Kaniyan.AI detected {len(alerts)} configured alert(s) for {location_label}. "
             "These are app-generated, not official warnings:"]
    for a in alerts[:6]:
        lines.append(f"- {a.when}: {a.variable} = {a.value:g} {a.unit} ({a.level.label}).")
        for tip in list(a.advice)[:2]:
            lines.append(f"  Precaution: {tip}")
    if len(alerts) > 6:
        lines.append(f"- {len(alerts) - 6} additional alert(s) are listed in the Alerts tab.")
    lines.append("Check official IMD, CPCB, and local authority updates before making safety decisions.")
    return "\n".join(lines)


def _groq_client(api_key=None):
    from groq import Groq
    return Groq(api_key=api_key or _get_api_key(), timeout=20.0)


def _call_groq(messages, client=None):
    if client is None:
        key = _get_api_key()
        if not key:
            raise RuntimeError("No GROQ_API_KEY configured")
        client = _groq_client(key)
    params = dict(model=_get_model(), messages=messages, temperature=0.3,
                  max_tokens=1024)  # headroom: gpt-oss models spend some tokens on reasoning
    try:
        response = client.chat.completions.create(reasoning_effort="low", **params)
    except Exception as exc:
        # Some models reject reasoning_effort; retry once without it on a 400 error only.
        if type(exc).__name__ != "BadRequestError":
            raise
        response = client.chat.completions.create(**params)
    return (response.choices[0].message.content or "").strip()


def explain(location_label, weather, air, alerts, use_llm=True, client=None) -> Explanation:
    is_sample = bool(getattr(weather, "is_sample", False))
    fallback = fallback_explanation(location_label, alerts, is_sample)
    if not use_llm:
        return Explanation(fallback, "Python fallback", "AI explanations are switched off.")
    if client is None and not _get_api_key():
        return Explanation(fallback, "Python fallback", "No GROQ_API_KEY found; add it to Streamlit secrets to enable AI.")
    payload = build_payload(location_label, weather, air, alerts)
    try:
        answer = _call_groq([
            {"role": "system", "content": SYSTEM_PROMPT + " Explain the current conditions and practical precautions in at most 140 words."},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ], client=client)
    except Exception as exc:
        return Explanation(fallback, "Python fallback", f"Groq unavailable ({type(exc).__name__}).")
    if not answer:
        return Explanation(fallback, "Python fallback", "AI returned an empty answer.")
    return Explanation(answer, "Groq AI")


def chat_answer(question, location_label, weather, air, alerts, history=None, client=None) -> Explanation:
    """Answer one chat question grounded in current Kaniyan.AI data."""
    q = (question or "").strip()
    if not q:
        return Explanation("Please enter a question about the current weather, air quality, alerts, or precautions.", "Python fallback")
    payload = build_payload(location_label, weather, air, alerts)
    fallback = fallback_explanation(location_label, alerts, bool(getattr(weather, "is_sample", False)))
    if client is None and not _get_api_key():
        return Explanation(
            "AI chat is not configured yet because GROQ_API_KEY is missing. Here is the current rule-based summary instead:\n\n" + fallback,
            "Python fallback", "Add GROQ_API_KEY to Streamlit secrets to enable conversational answers.")
    messages = [{"role": "system", "content": SYSTEM_PROMPT + " Answer the user's question directly, starting with the answer itself. Usually 3-6 short sentences or bullets. Current Kaniyan.AI context (JSON) follows: " + json.dumps(payload, ensure_ascii=False)}]
    for item in (history or [])[-8:]:
        role = item.get("role")
        content = item.get("content", "")
        if role in ("user", "assistant") and isinstance(content, str):
            messages.append({"role": role, "content": content[:1500]})
    messages.append({"role": "user", "content": q[:1500]})
    try:
        answer = _call_groq(messages, client=client)
    except Exception as exc:
        return Explanation("I can't reach the AI service right now. " + fallback, "Python fallback", f"Groq unavailable ({type(exc).__name__}).")
    if not answer:
        return Explanation("I didn't receive an AI response. " + fallback, "Python fallback", "AI returned an empty answer.")
    return Explanation(answer, "Groq AI")
