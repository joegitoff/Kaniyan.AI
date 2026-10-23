"""
config.py - central settings for Kaniyan.AI.

Python concepts: constants, dictionaries, enums (IntEnum), module-level configuration.

IMPORTANT: The thresholds below are ILLUSTRATIVE values chosen for a student
project. They are loosely inspired by commonly published categories (for example
IMD daily-rainfall classes and the US EPA AQI bands) but they are NOT official
warning criteria. Always follow official advisories (IMD, state disaster
management authorities, CPCB) for real decisions.
"""
from enum import IntEnum


class Level(IntEnum):
    """Warning levels. IntEnum lets us sort and compare levels (HIGH > CAUTION)."""
    INFO = 1
    CAUTION = 2
    HIGH = 3

    @property
    def label(self) -> str:
        return {1: "Information", 2: "Caution", 3: "High concern"}[int(self)]


LEVEL_DEFINITIONS = {
    Level.INFO: "A value is above a normal/comfortable range. Be aware; no action usually needed.",
    Level.CAUTION: "A value is high enough that sensitive people or outdoor plans may need precautions.",
    Level.HIGH: "A value is very high on our scale. Take precautions and check official sources.",
}

# --- Data-source endpoints (verified against Open-Meteo documentation) --------
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
REQUEST_TIMEOUT_SECONDS = 10

FORECAST_DAYS = 7          # weather: API supports up to 16
AIR_QUALITY_DAYS = 5       # air quality: API default is 5, maximum 7

DEFAULT_CITY = "Chennai"
QUICK_CITIES = ["Chennai", "Thanjavur", "Madurai", "Coimbatore", "Tiruchirappalli",
                "Salem", "Tirunelveli", "Vellore", "Bengaluru", "Mumbai", "Delhi"]

# --- Alert thresholds (illustrative, editable from the app sidebar) ----------
# Each rule has three cut-offs. A value >= cut-off triggers that level.
DEFAULT_THRESHOLDS = {
    "rain_daily_mm":    {"info": 15.6, "caution": 64.5, "high": 115.6},   # mm per day
    "temp_max_c":       {"info": 35.0, "caution": 38.0, "high": 40.0},    # deg C
    "feels_like_max_c": {"info": 38.0, "caution": 41.0, "high": 46.0},    # deg C
    "wind_gust_kmh":    {"info": 40.0, "caution": 60.0, "high": 80.0},    # km/h
    "us_aqi":           {"info": 51.0, "caution": 101.0, "high": 151.0},  # US AQI scale
}

THRESHOLD_LABELS = {
    "rain_daily_mm": "Daily rainfall total (mm)",
    "temp_max_c": "Daily maximum temperature (°C)",
    "feels_like_max_c": "Daily maximum 'feels-like' temperature (°C)",
    "wind_gust_kmh": "Daily maximum wind gust (km/h)",
    "us_aqi": "Air quality index (US AQI scale)",
}

THRESHOLD_NOTE = (
    "Thresholds are illustrative and editable. They are not official warning criteria. "
    "AQI is on the US AQI scale as computed by the Open-Meteo/CAMS model - it is not the "
    "Indian CPCB National AQI and not a ground-station reading."
)

# WMO weather interpretation codes (copied from the Open-Meteo documentation)
WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snowfall", 73: "Moderate snowfall", 75: "Heavy snowfall", 77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 97: "Heavy thunderstorm",
    99: "Thunderstorm with heavy hail",
}

# US AQI category bands (as documented by Open-Meteo)
US_AQI_BANDS = [
    (50, "Good"), (100, "Moderate"), (150, "Unhealthy for sensitive groups"),
    (200, "Unhealthy"), (300, "Very unhealthy"), (500, "Hazardous"),
]

ATTRIBUTION = (
    "Weather data: Open-Meteo.com (CC BY 4.0), combining national weather-service models. "
    "Air quality: Open-Meteo Air Quality API using CAMS (Copernicus Atmosphere Monitoring "
    "Service) model data. Locations: GeoNames via the Open-Meteo Geocoding API. "
    "Open-Meteo's free API is for non-commercial use."
)
