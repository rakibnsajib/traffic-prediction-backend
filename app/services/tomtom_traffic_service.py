from __future__ import annotations

import os
from math import asin, cos, radians, sin, sqrt
from threading import Lock
from time import monotonic

import httpx


TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY", "")
TOMTOM_FLOW_URL = os.getenv(
    "TOMTOM_FLOW_URL",
    "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json",
)
TOMTOM_ROUTING_URL = os.getenv(
    "TOMTOM_ROUTING_URL",
    "https://api.tomtom.com/routing/1/calculateRoute",
)
TOMTOM_TRAFFIC_TIMEOUT_SECONDS = float(
    os.getenv("TOMTOM_TRAFFIC_TIMEOUT_SECONDS", "3")
)
TOMTOM_TRAFFIC_CACHE_SECONDS = int(
    os.getenv("TOMTOM_TRAFFIC_CACHE_SECONDS", "60")
)


class TomTomTrafficService:
    def __init__(self) -> None:
        self._cache: dict[
            tuple[float, float],
            tuple[float, float | None],
        ] = {}
        self._cache_lock = Lock()

    @staticmethod
    def _segment_midpoint(
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

    @staticmethod
    def _valid_points(
        coordinates: list[list[float]] | None,
    ) -> list[tuple[float, float]]:
        if not coordinates:
            return []
        try:
            return [
                (float(point[1]), float(point[0]))
                for point in coordinates
                if len(point) >= 2
                and -180 <= float(point[0]) <= 180
                and -90 <= float(point[1]) <= 90
            ]
        except (TypeError, ValueError):
            return []

    @staticmethod
    def _haversine_meters(
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> float:
        lat1, lng1 = map(radians, start)
        lat2, lng2 = map(radians, end)
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        value = (
            sin(dlat / 2) ** 2
            + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
        )
        return 6371000 * 2 * asin(sqrt(value))

    def _flow_speed(
        self,
        midpoint: tuple[float, float],
    ) -> float | None:
        with httpx.Client(timeout=TOMTOM_TRAFFIC_TIMEOUT_SECONDS) as client:
            response = client.get(
                TOMTOM_FLOW_URL,
                params={
                    "key": TOMTOM_API_KEY,
                    "point": f"{midpoint[0]},{midpoint[1]}",
                    "unit": "KMPH",
                },
            )
            response.raise_for_status()
            flow = response.json().get("flowSegmentData", {})
            speed = float(flow["currentSpeed"])
        return speed if 3 <= speed <= 130 else None

    def _routing_speed(
        self,
        points: list[tuple[float, float]],
    ) -> float | None:
        if len(points) < 2:
            return None
        start = points[0]
        end = points[-1]
        direct_distance = self._haversine_meters(start, end)
        if direct_distance < 20:
            return None

        locations = f"{start[0]},{start[1]}:{end[0]},{end[1]}"
        url = f"{TOMTOM_ROUTING_URL}/{locations}/json"
        with httpx.Client(timeout=TOMTOM_TRAFFIC_TIMEOUT_SECONDS) as client:
            response = client.get(
                url,
                params={
                    "key": TOMTOM_API_KEY,
                    "traffic": "true",
                    "travelMode": "car",
                    "routeType": "fastest",
                    "computeTravelTimeFor": "all",
                },
            )
            response.raise_for_status()
            summary = response.json()["routes"][0]["summary"]
            route_distance = float(summary["lengthInMeters"])
            duration = float(summary["travelTimeInSeconds"])

        # Reject aggressive road snapping to a different nearby road.
        if (
            duration <= 0
            or route_distance < direct_distance * 0.7
            or route_distance > direct_distance * 4
        ):
            return None
        speed = route_distance / duration * 3.6
        return speed if 3 <= speed <= 130 else None

    def current_speed_kmph(
        self,
        coordinates: list[list[float]] | None,
    ) -> float | None:
        if not TOMTOM_API_KEY:
            return None

        points = self._valid_points(coordinates)
        midpoint = self._segment_midpoint(coordinates)
        if midpoint is None or not points:
            return None

        cache_key = (round(midpoint[0], 4), round(midpoint[1], 4))
        now = monotonic()
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached and now - cached[0] < TOMTOM_TRAFFIC_CACHE_SECONDS:
                return cached[1]

        try:
            speed = self._flow_speed(midpoint)
        except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError):
            speed = None

        if speed is None:
            try:
                speed = self._routing_speed(points)
            except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError):
                speed = None

        if speed is None:
            with self._cache_lock:
                self._cache[cache_key] = (now, None)
            return None

        with self._cache_lock:
            self._cache[cache_key] = (now, speed)
        return speed


tomtom_traffic_service = TomTomTrafficService()
