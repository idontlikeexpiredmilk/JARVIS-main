"""Optional weather lookup for the system dashboard.

Uses the free OpenWeatherMap "current weather" endpoint. Weather is entirely
optional: if it is disabled, unconfigured, or the network call fails, callers
simply get ``None`` back and the rest of JARVIS keeps working normally.

API keys are never hard-coded; they are read from the environment
(JARVIS_WEATHER_API_KEY or OPENWEATHER_API_KEY) via config.py.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from config import CONFIG

WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


@dataclass(frozen=True)
class WeatherSnapshot:
    temperature: float
    description: str
    location: str
    units: str

    @property
    def temperature_label(self) -> str:
        unit_symbol = "F" if self.units == "imperial" else "C"
        return f"{self.temperature:.0f}\u00b0{unit_symbol}"


class WeatherService:
    """Fetches current weather. Safe to call from a background thread."""

    @property
    def enabled(self) -> bool:
        return bool(CONFIG.enable_weather and CONFIG.weather_api_key and CONFIG.weather_location)

    def fetch(self) -> WeatherSnapshot | None:
        """Return a weather snapshot, or None if weather is unavailable.

        Never raises: any misconfiguration or network failure results in
        None so the dashboard can just show "Unavailable" instead of
        breaking JARVIS.
        """
        if not self.enabled:
            return None
        try:
            params = {
                "q": CONFIG.weather_location,
                "appid": CONFIG.weather_api_key,
                "units": CONFIG.weather_units,
            }
            url = f"{WEATHER_URL}?{urllib.parse.urlencode(params)}"
            request = urllib.request.Request(url, headers={"User-Agent": "JARVIS-Desktop-Assistant/0.1"})
            with urllib.request.urlopen(request, timeout=8) as response:
                data = json.loads(response.read().decode("utf-8"))
            main = data.get("main", {})
            weather_list = data.get("weather", [])
            description = ""
            if weather_list and isinstance(weather_list, list):
                description = str(weather_list[0].get("description", "")).title()
            temperature = float(main.get("temp", 0.0))
            location_name = str(data.get("name", CONFIG.weather_location))
            return WeatherSnapshot(
                temperature=temperature,
                description=description or "Unknown",
                location=location_name,
                units=CONFIG.weather_units,
            )
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, OSError):
            return None
