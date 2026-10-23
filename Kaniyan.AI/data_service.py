"""
data_service.py - talks to the Open-Meteo APIs and turns JSON into pandas tables.

Python concepts: functions, requests library, exceptions (custom classes),
dataclasses, dictionaries/lists, pandas DataFrames, datetime, type hints.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
import requests

import config


# ---------------------------------------------------------------- exceptions --
class DataServiceError(Exception):
    """Base class: anything that goes wrong while getting data."""


class NetworkError(DataServiceError):
    """No internet, DNS problem or timeout."""


class RateLimitError(DataServiceError):
    """HTTP 429: too many requests."""


class LocationNotFoundError(DataServiceError):
    """Geocoding returned nothing for the typed name."""


class DataFormatError(DataServiceError):
    """The API answered, but the JSON is not in the shape we expect."""


# --------------------------------------------------------------- data classes --
@dataclass
class Location:
    name: str
    latitude: float
    longitude: float
    country: str = ""
    admin1: str = ""          # state / region
    timezone: str = "auto"

    @property
    def label(self) -> str:
        parts = [p for p in (self.name, self.admin1, self.country) if p]
        return ", ".join(parts)


@dataclass
class WeatherData:
    location: Location
    current: dict
    daily: pd.DataFrame
    hourly: pd.DataFrame
    units: dict
    timezone: str
    fetched_at: datetime
    source: str = "Open-Meteo Weather Forecast API (api.open-meteo.com/v1/forecast)"
    is_sample: bool = False


@dataclass
class AirQualityData:
    location: Location
    current: dict
    hourly: pd.DataFrame
    units: dict
    fetched_at: datetime
    source: str = ("Open-Meteo Air Quality API (CAMS model data) - model estimate, "
                   "not a government monitoring-station reading")
    is_sample: bool = False


# ------------------------------------------------------------------ HTTP part --
def _get_json(url: str, params: dict) -> dict:
    """Call an API and return parsed JSON, or raise one of our own exceptions."""
    try:
        response = requests.get(url, params=params, timeout=config.REQUEST_TIMEOUT_SECONDS)
    except requests.exceptions.Timeout as exc:
        raise NetworkError("The data service took too long to respond (timeout).") from exc
    except requests.exceptions.ConnectionError as exc:
        raise NetworkError("Could not connect. Check your internet connection.") from exc
    except requests.exceptions.RequestException as exc:
        raise NetworkError(f"Network problem: {exc}") from exc

    if response.status_code == 429:
        raise RateLimitError("Too many requests to the data service. Wait a minute and retry.")

    try:
        data = response.json()
    except ValueError as exc:
        raise DataFormatError("The data service returned something that is not valid JSON.") from exc

    if response.status_code >= 400 or (isinstance(data, dict) and data.get("error")):
        reason = data.get("reason", "unknown reason") if isinstance(data, dict) else "unknown reason"
        raise DataServiceError(f"The API reported an error (HTTP {response.status_code}): {reason}")

    if not isinstance(data, dict):
        raise DataFormatError("Unexpected JSON structure (expected an object).")
    return data


# ------------------------------------------------------------------ geocoding --
def search_locations(query: str, count: int = 5) -> list[Location]:
    """Convert a city name into up to `count` candidate locations."""
    query = (query or "").strip()
    if len(query) < 2:
        raise LocationNotFoundError("Please type at least 2 characters of a place name.")

    data = _get_json(config.GEOCODING_URL, {"name": query, "count": count,
                                            "language": "en", "format": "json"})
    results = data.get("results") or []   # the API omits "results" when nothing is found
    locations = []
    for item in results:
        if item.get("latitude") is None or item.get("longitude") is None:
            continue                       # skip incomplete records safely
        locations.append(Location(
            name=item.get("name", query),
            latitude=float(item["latitude"]),
            longitude=float(item["longitude"]),
            country=item.get("country", ""),
            admin1=item.get("admin1", ""),
            timezone=item.get("timezone", "auto"),
        ))
    if not locations:
        raise LocationNotFoundError(f"No place found for '{query}'. Check the spelling or try a nearby city.")
    return locations


# -------------------------------------------------------------- table helpers --
def _frame_from_block(block: Optional[dict], time_column: str) -> pd.DataFrame:
    """Turn {'time': [...], 'x': [...]} into a DataFrame; bad/missing values become NaN."""
    if not block or "time" not in block:
        return pd.DataFrame()
    length = len(block["time"])
    for key, values in block.items():
        if len(values) != length:
            raise DataFormatError(f"Column '{key}' has {len(values)} values but 'time' has {length}.")
    df = pd.DataFrame(block).rename(columns={"time": time_column})
    df[time_column] = pd.to_datetime(df[time_column], errors="coerce")
    for column in df.columns:
        if column != time_column:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df.dropna(subset=[time_column]).reset_index(drop=True)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------- weather --
def parse_weather(raw: dict, location: Location, fetched_at: Optional[datetime] = None,
                  is_sample: bool = False) -> WeatherData:
    """Pure function (no network): raw API JSON -> WeatherData. Easy to unit-test."""
    if not isinstance(raw, dict) or "daily" not in raw:
        raise DataFormatError("Weather response has no 'daily' section.")
    daily = _frame_from_block(raw.get("daily"), "date")
    hourly = _frame_from_block(raw.get("hourly"), "time")
    if daily.empty:
        raise DataFormatError("Weather response contains no daily forecast rows.")

    current = dict(raw.get("current") or {})
    code = current.get("weather_code")
    current["weather_text"] = config.WMO_CODES.get(int(code), "Unknown") if code is not None else "Unavailable"
    if not daily.empty and "weather_code" in daily.columns:
        daily["weather_text"] = daily["weather_code"].map(
            lambda c: config.WMO_CODES.get(int(c), "Unknown") if pd.notna(c) else "Unavailable")

    units = {}
    for key in ("current_units", "daily_units", "hourly_units"):
        units.update(raw.get(key) or {})

    return WeatherData(location=location, current=current, daily=daily, hourly=hourly,
                       units=units, timezone=raw.get("timezone", "unknown"),
                       fetched_at=fetched_at or _now_utc(), is_sample=is_sample)


def fetch_weather(location: Location, forecast_days: int = config.FORECAST_DAYS) -> WeatherData:
    params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,"
                   "weather_code,wind_speed_10m,wind_gusts_10m",
        "hourly": "temperature_2m,precipitation,precipitation_probability,wind_speed_10m,wind_gusts_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,apparent_temperature_max,"
                 "precipitation_sum,precipitation_probability_max,wind_speed_10m_max,"
                 "wind_gusts_10m_max,uv_index_max",
        "timezone": "auto",
        "forecast_days": forecast_days,
    }
    return parse_weather(_get_json(config.FORECAST_URL, params), location)


# --------------------------------------------------------------- air quality --
def parse_air_quality(raw: dict, location: Location, fetched_at: Optional[datetime] = None,
                      is_sample: bool = False) -> AirQualityData:
    """Pure function: raw air-quality JSON -> AirQualityData."""
    if not isinstance(raw, dict) or "hourly" not in raw:
        raise DataFormatError("Air-quality response has no 'hourly' section.")
    hourly = _frame_from_block(raw.get("hourly"), "time")
    if hourly.empty:
        raise DataFormatError("Air-quality response contains no hourly rows.")
    units = {}
    for key in ("current_units", "hourly_units"):
        units.update(raw.get(key) or {})
    return AirQualityData(location=location, current=dict(raw.get("current") or {}),
                          hourly=hourly, units=units,
                          fetched_at=fetched_at or _now_utc(), is_sample=is_sample)


def fetch_air_quality(location: Location, forecast_days: int = config.AIR_QUALITY_DAYS) -> AirQualityData:
    params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "current": "us_aqi,european_aqi,pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,"
                   "sulphur_dioxide,ozone",
        "hourly": "pm10,pm2_5,us_aqi,european_aqi",
        "timezone": "auto",
        "forecast_days": forecast_days,
    }
    return parse_air_quality(_get_json(config.AIR_QUALITY_URL, params), location)


# ------------------------------------------------------------------ utilities --
def aqi_category_us(value: Any) -> str:
    """Name of the US AQI band for a number, or 'Unavailable'."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Unavailable"
    if number != number:          # NaN check
        return "Unavailable"
    for upper, name in config.US_AQI_BANDS:
        if number <= upper:
            return name
    return "Hazardous"
