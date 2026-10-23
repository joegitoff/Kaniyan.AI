"""
charts.py - Plotly figures used by the dashboard.

Python concepts: functions returning objects, Plotly graph_objects, DataFrames.
Dashed lines show the configured "caution" threshold so users see WHY an alert fires.
"""
import pandas as pd
import plotly.graph_objects as go


def _style(fig: go.Figure, title: str, y_title: str) -> go.Figure:
    fig.update_layout(title=title, yaxis_title=y_title, height=340, margin=dict(l=10, r=10, t=50, b=10),
                      legend=dict(orientation="h", y=-0.2), hovermode="x unified")
    return fig


def temperature_chart(daily: pd.DataFrame, caution_c: float) -> go.Figure:
    fig = go.Figure()
    if "temperature_2m_max" in daily:
        fig.add_trace(go.Scatter(x=daily["date"], y=daily["temperature_2m_max"], name="Max temp", mode="lines+markers"))
    if "temperature_2m_min" in daily:
        fig.add_trace(go.Scatter(x=daily["date"], y=daily["temperature_2m_min"], name="Min temp", mode="lines+markers"))
    if "apparent_temperature_max" in daily:
        fig.add_trace(go.Scatter(x=daily["date"], y=daily["apparent_temperature_max"], name="Max feels-like",
                                 mode="lines", line=dict(dash="dot")))
    fig.add_hline(y=caution_c, line_dash="dash", line_color="orange",
                  annotation_text=f"Caution rule: {caution_c:g} °C", annotation_position="top left")
    return _style(fig, "Daily temperature forecast", "°C")


def rainfall_chart(daily: pd.DataFrame, caution_mm: float) -> go.Figure:
    fig = go.Figure()
    if "precipitation_sum" in daily:
        fig.add_trace(go.Bar(x=daily["date"], y=daily["precipitation_sum"], name="Rain (mm)"))
    fig.add_hline(y=caution_mm, line_dash="dash", line_color="orange",
                  annotation_text=f"Caution rule: {caution_mm:g} mm/day", annotation_position="top left")
    return _style(fig, "Daily rainfall forecast (model estimate, not a flood prediction)", "mm")


def wind_chart(daily: pd.DataFrame, caution_kmh: float) -> go.Figure:
    fig = go.Figure()
    if "wind_speed_10m_max" in daily:
        fig.add_trace(go.Bar(x=daily["date"], y=daily["wind_speed_10m_max"], name="Max wind"))
    if "wind_gusts_10m_max" in daily:
        fig.add_trace(go.Scatter(x=daily["date"], y=daily["wind_gusts_10m_max"], name="Max gust", mode="lines+markers"))
    fig.add_hline(y=caution_kmh, line_dash="dash", line_color="orange",
                  annotation_text=f"Caution rule (gust): {caution_kmh:g} km/h", annotation_position="top left")
    return _style(fig, "Daily wind forecast", "km/h")


def aqi_chart(hourly: pd.DataFrame, info: float, caution: float, high: float) -> go.Figure:
    fig = go.Figure()
    if "us_aqi" in hourly:
        fig.add_trace(go.Scatter(x=hourly["time"], y=hourly["us_aqi"], name="US AQI (model)", mode="lines"))
    for value, label, colour in ((info, "Info", "gold"), (caution, "Caution", "orange"), (high, "High concern", "red")):
        fig.add_hline(y=value, line_dash="dash", line_color=colour, annotation_text=f"{label}: {value:g}",
                      annotation_position="top left")
    return _style(fig, "Hourly air-quality index forecast (US AQI scale, CAMS model)", "US AQI")


def pm_chart(hourly: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for column, name in (("pm2_5", "PM2.5"), ("pm10", "PM10")):
        if column in hourly:
            fig.add_trace(go.Scatter(x=hourly["time"], y=hourly[column], name=name, mode="lines"))
    return _style(fig, "Particulate matter concentrations (µg/m³, model)", "µg/m³")
