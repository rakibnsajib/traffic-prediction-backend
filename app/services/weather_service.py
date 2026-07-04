from __future__ import annotations

from dataclasses import dataclass
import os
from threading import Lock
from time import monotonic

import httpx


OPEN_METEO_URL = os.getenv(
    "OPEN_METEO_URL",
    "https://api.open-meteo.com/v1/forecast",
)
OPEN_METEO_TIMEOUT_SECONDS = float(
    os.getenv("OPEN_METEO_TIMEOUT_SECONDS", "3")
)
OPEN_METEO_CACHE_SECONDS = int(
    os.getenv("OPEN_METEO_CACHE_SECONDS", "300")
)


@dataclass(frozen=True)
class WeatherObservation:
    temperature_c: float
    relative_humidity: float
    precipitation_mm: float
    wind_speed_kmph: float
    is_rain: int
    is_fog: int
    is_cloudy: int
    weather_code: int


def weather_flags_from_wmo(code: int) -> tuple[int, int, int]:
    is_fog = int(code in {45, 48})
    is_rain = int(
        code in {
            51,
            53,
            55,
            56,
            57,
            61,
            63,
            65,
            66,
            67,
            80,
            81,
            82,
            95,
            96,
            99,
        }
    )
    is_cloudy = int(code in {1, 2, 3} or is_fog or is_rain)
    return is_rain, is_fog, is_cloudy


class OpenMeteoWeatherService:
    def __init__(self) -> None:
        self._cache: dict[
            tuple[float, float],
            tuple[float, WeatherObservation | None],
        ] = {}
        self._cache_lock = Lock()

    @staticmethod
    def _midpoint(
        coordinates: list[list[float]] | None,
    ) -> tuple[float, float] | None:
        if not coordinates:
            return None
        try:
            valid = [
                point
                for point in coordinates
                if len(point) >= 2
                and -180 <= float(point[0]) <= 180
                and -90 <= float(point[1]) <= 90
            ]
        except (TypeError, ValueError):
            return None
        if not valid:
            return None
        point = valid[len(valid) // 2]
        return float(point[1]), float(point[0])

    def current_weather(
        self,
        coordinates: list[list[float]] | None,
    ) -> WeatherObservation | None:
        midpoint = self._midpoint(coordinates)
        if midpoint is None:
            return None

        # Weather changes much more slowly than traffic, so nearby segments
        # deliberately share a cached observation.
        cache_key = (round(midpoint[0], 2), round(midpoint[1], 2))
        now = monotonic()
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached and now - cached[0] < OPEN_METEO_CACHE_SECONDS:
                return cached[1]

        try:
            with httpx.Client(timeout=OPEN_METEO_TIMEOUT_SECONDS) as client:
                response = client.get(
                    OPEN_METEO_URL,
                    params={
                        "latitude": midpoint[0],
                        "longitude": midpoint[1],
                        "current": (
                            "weather_code,rain,precipitation,temperature_2m,"
                            "relative_humidity_2m,wind_speed_10m"
                        ),
                        "timezone": "auto",
                        "forecast_days": 1,
                    },
                )
                response.raise_for_status()
                current = response.json()["current"]
                code = int(current["weather_code"])
                is_rain, is_fog, is_cloudy = weather_flags_from_wmo(code)
                observation = WeatherObservation(
                    temperature_c=float(current["temperature_2m"]),
                    relative_humidity=float(current["relative_humidity_2m"]),
                    precipitation_mm=float(current["precipitation"]),
                    wind_speed_kmph=float(current["wind_speed_10m"]),
                    is_rain=is_rain,
                    is_fog=is_fog,
                    is_cloudy=is_cloudy,
                    weather_code=code,
                )
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            observation = None

        with self._cache_lock:
            self._cache[cache_key] = (now, observation)
        return observation


weather_service = OpenMeteoWeatherService()
