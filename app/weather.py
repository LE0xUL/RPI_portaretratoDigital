import time

import httpx

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_TTL_SECONDS = 15 * 60

_cache: dict[tuple[float, float, str], tuple[float, dict]] = {}


def get_weather(latitude: float, longitude: float, units: str = "metric") -> dict | None:
    key = (round(latitude, 3), round(longitude, 3), units)
    cached = _cache.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    temperature_unit = "fahrenheit" if units == "imperial" else "celsius"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,weather_code",
        "temperature_unit": temperature_unit,
        "timezone": "auto",
    }
    try:
        resp = httpx.get(OPEN_METEO_URL, params=params, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return cached[1] if cached else None

    current = data.get("current", {})
    result = {
        "temperature": current.get("temperature_2m"),
        "weather_code": current.get("weather_code"),
        "units": units,
    }
    _cache[key] = (now, result)
    return result
