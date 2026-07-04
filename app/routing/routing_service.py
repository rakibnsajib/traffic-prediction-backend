from __future__ import annotations

import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from itertools import islice
from math import atan2, cos, radians, sin, sqrt

import httpx
import networkx as nx

from app.ml.model_service import traffic_predictor
from app.routing.graph_data import INTERSECTIONS, ROAD_SEGMENTS


OSRM_BASE_URL = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
GOOGLE_MAPS_DIRECTIONS_URL = os.getenv(
    "GOOGLE_MAPS_DIRECTIONS_URL", "https://maps.googleapis.com/maps/api/directions/json"
)
GOOGLE_ROUTES_API_URL = os.getenv(
    "GOOGLE_ROUTES_API_URL", "https://routes.googleapis.com/directions/v2:computeRoutes"
)
MAX_ROUTE_ALTERNATIVES = int(os.getenv("MAX_ROUTE_ALTERNATIVES", "6"))


class GoogleRoutingError(RuntimeError):
    pass


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return r * c


def _duration_seconds(value: object) -> float:
    if not value:
        return 0.0
    try:
        return float(str(value).removesuffix("s"))
    except (TypeError, ValueError):
        return 0.0


def _geometry_distance_km(coordinates: list[list[float]]) -> float:
    return sum(
        _haversine(
            coordinates[index][1],
            coordinates[index][0],
            coordinates[index + 1][1],
            coordinates[index + 1][0],
        )
        for index in range(len(coordinates) - 1)
    )


GOOGLE_TRAFFIC_LEVELS = {
    "NORMAL": "Low",
    "SLOW": "Medium",
    "TRAFFIC_JAM": "High",
}

GOOGLE_TRAFFIC_SPEED_FACTORS = {
    "NORMAL": 1.0,
    "SLOW": 0.55,
    "TRAFFIC_JAM": 0.25,
}


def nearest_intersection(lat: float, lng: float) -> str:
    return min(
        INTERSECTIONS.keys(),
        key=lambda node: _haversine(
            lat,
            lng,
            INTERSECTIONS[node]["lat"],
            INTERSECTIONS[node]["lng"],
        ),
    )


def _decode_polyline(encoded: str) -> list[list[float]]:
    coordinates: list[list[float]] = []
    index = 0
    lat = 0
    lng = 0

    while index < len(encoded):
        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if result & 1 else result >> 1
        lat += dlat

        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if result & 1 else result >> 1
        lng += dlng

        coordinates.append([lng / 1e5, lat / 1e5])

    return coordinates


def _road_geometry_fallback(start_node: str, end_node: str) -> list[list[float]]:
    start = INTERSECTIONS[start_node]
    end = INTERSECTIONS[end_node]
    return [[start["lng"], start["lat"]], [end["lng"], end["lat"]]]


def _anchor_segments_to_request(
    segments: list[dict],
    source_lat: float,
    source_lng: float,
    destination_lat: float,
    destination_lng: float,
) -> list[dict]:
    if not segments:
        return segments

    anchored = [{**segment, "coordinates": list(segment.get("coordinates", []))} for segment in segments]
    source_point = [source_lng, source_lat]
    destination_point = [destination_lng, destination_lat]

    first_coordinates = anchored[0]["coordinates"]
    if first_coordinates and first_coordinates[0] != source_point:
        anchored[0]["coordinates"] = [source_point, *first_coordinates]

    last_coordinates = anchored[-1]["coordinates"]
    if last_coordinates and last_coordinates[-1] != destination_point:
        anchored[-1]["coordinates"] = [*last_coordinates, destination_point]

    return anchored


@lru_cache(maxsize=256)
def road_geometry_between_nodes(start_node: str, end_node: str) -> list[list[float]]:
    start = INTERSECTIONS[start_node]
    end = INTERSECTIONS[end_node]
    if GOOGLE_MAPS_API_KEY:
        params = {
            "origin": f"{start['lat']},{start['lng']}",
            "destination": f"{end['lat']},{end['lng']}",
            "mode": "driving",
            "alternatives": "false",
            "key": GOOGLE_MAPS_API_KEY,
        }
        try:
            with httpx.Client(timeout=3.0) as client:
                response = client.get(GOOGLE_MAPS_DIRECTIONS_URL, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            payload = None

        if payload and payload.get("status") == "OK":
            routes = payload.get("routes", [])
            if routes:
                encoded = routes[0].get("overview_polyline", {}).get("points", "")
                if encoded:
                    geometry = _decode_polyline(encoded)
                    if len(geometry) >= 2:
                        return geometry

    url = f"{OSRM_BASE_URL}/route/v1/driving/{start['lng']},{start['lat']};{end['lng']},{end['lat']}"
    params = {
        "alternatives": "false",
        "steps": "false",
        "overview": "full",
        "geometries": "geojson",
        "annotations": "false",
    }
    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return _road_geometry_fallback(start_node, end_node)

    routes = payload.get("routes", [])
    if not routes:
        return _road_geometry_fallback(start_node, end_node)

    geometry = routes[0].get("geometry", {}).get("coordinates", [])
    if len(geometry) < 2:
        return _road_geometry_fallback(start_node, end_node)
    return geometry


class RouterService:
    def __init__(self) -> None:
        self.base_graph = nx.Graph()
        edge_pairs: list[tuple[str, str]] = []
        for segment in ROAD_SEGMENTS:
            from_node = segment["from_node"]
            to_node = segment["to_node"]
            self.base_graph.add_edge(
                from_node,
                to_node,
                segment_id=segment["segment_id"],
                distance_km=segment["distance_km"],
            )
            edge_pairs.append((from_node, to_node))

        if edge_pairs:
            max_workers = min(8, len(edge_pairs))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                geometries = executor.map(lambda pair: road_geometry_between_nodes(*pair), edge_pairs)
                for (start_node, end_node), coordinates in zip(edge_pairs, geometries):
                    self.base_graph[start_node][end_node]["coordinates"] = coordinates

    @staticmethod
    def _aggregate(segments: list[dict]) -> tuple[float, float]:
        total_distance = round(sum(s["distance_km"] for s in segments), 2)
        total_time = round(sum(s["predicted_travel_time_min"] for s in segments), 2)
        return total_distance, total_time

    @staticmethod
    def _overall_traffic_level(segments: list[dict]) -> str:
        if not segments:
            return "Low"
        levels = [s["congestion_level"] for s in segments]
        if "High" in levels:
            return "High"
        if "Medium" in levels:
            return "Medium"
        return "Low"

    def _score_route(self, segments: list[dict]) -> tuple[float, float]:
        distance, predicted_time = self._aggregate(segments)
        return predicted_time, distance

    def _route_response(
        self,
        optimal_segments: list[dict],
        shortest_segments: list[dict],
        alternatives: list[dict] | None = None,
    ) -> dict:
        shortest_distance, shortest_time = self._aggregate(shortest_segments)
        optimal_distance, optimal_time = self._aggregate(optimal_segments)
        raw_saved = max(shortest_time - optimal_time, 0)
        if raw_saved <= 0 and alternatives:
            ai_route = next((r for r in alternatives if r.get("is_ai_optimal")), None)
            if ai_route:
                next_best = sorted(
                    [r for r in alternatives if r.get("route_id") != ai_route.get("route_id")],
                    key=lambda r: r.get("total_time_min", 10**9),
                )
                if next_best:
                    raw_saved = max(next_best[0].get("total_time_min", 0) - optimal_time, 0)

        return {
            "optimal_route": optimal_segments,
            "shortest_route": shortest_segments,
            "eta_minutes": round(optimal_time, 2),
            "distance_km": round(optimal_distance, 2),
            "traffic_level": self._overall_traffic_level(optimal_segments),
            "time_saved_minutes": round(raw_saved, 2),
            "comparison": [
                {
                    "route_name": "ai_optimal",
                    "segments": optimal_segments,
                    "total_distance_km": optimal_distance,
                    "total_time_min": optimal_time,
                },
                {
                    "route_name": "shortest",
                    "segments": shortest_segments,
                    "total_distance_km": shortest_distance,
                    "total_time_min": shortest_time,
                },
            ],
            "alternatives": alternatives or [],
        }

    def _response_from_alternatives(self, alternatives: list[dict]) -> dict:
        normalized = [
            {
                **route,
                "is_shortest": False,
                "is_ai_optimal": False,
            }
            for route in alternatives
        ]
        shortest_i = min(range(len(normalized)), key=lambda i: normalized[i]["total_distance_km"])
        best_i = min(
            range(len(normalized)),
            key=lambda i: (normalized[i]["total_time_min"], normalized[i]["total_distance_km"]),
        )
        normalized[shortest_i]["is_shortest"] = True
        normalized[best_i]["is_ai_optimal"] = True
        return self._route_response(
            normalized[best_i]["segments"],
            normalized[shortest_i]["segments"],
            alternatives=normalized,
        )

    def _supplement_with_graph_alternatives(
        self,
        base_result: dict,
        source_lat: float,
        source_lng: float,
        destination_lat: float,
        destination_lng: float,
        departure_time: datetime,
    ) -> dict:
        existing_alts = list(base_result.get("alternatives") or [])
        if len(existing_alts) >= 2:
            return base_result

        graph_result = self._graph_fallback(
            source_lat, source_lng, destination_lat, destination_lng, departure_time
        )
        graph_alts = list(graph_result.get("alternatives") or [])
        if not graph_alts:
            return base_result

        existing_fingerprints = {
            tuple(seg.get("segment_id") for seg in alt.get("segments", [])) for alt in existing_alts
        }
        merged = list(existing_alts)
        for alt in graph_alts:
            fingerprint = tuple(seg.get("segment_id") for seg in alt.get("segments", []))
            if fingerprint in existing_fingerprints:
                continue
            merged.append(
                {
                    **alt,
                    "route_id": f"supp_{alt.get('route_id')}",
                }
            )
            existing_fingerprints.add(fingerprint)
            if len(merged) >= MAX_ROUTE_ALTERNATIVES:
                break

        if len(merged) <= len(existing_alts):
            return base_result
        return self._response_from_alternatives(merged)

    def _google_routes_api(
        self,
        source_lat: float,
        source_lng: float,
        destination_lat: float,
        destination_lng: float,
        departure_time: datetime,
        travel_mode: str,
    ) -> dict | None:
        if not GOOGLE_MAPS_API_KEY:
            return None

        headers = {
            "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
            "X-Goog-FieldMask": (
                "routes.distanceMeters,routes.duration,routes.staticDuration,"
                "routes.polyline.encodedPolyline,"
                "routes.travelAdvisory.speedReadingIntervals,"
                "routes.legs.steps.distanceMeters,routes.legs.steps.staticDuration,"
                "routes.legs.steps.polyline.encodedPolyline"
            ),
            "Content-Type": "application/json",
        }
        payload = {
            "origin": {
                "location": {
                    "latLng": {
                        "latitude": source_lat,
                        "longitude": source_lng,
                    }
                }
            },
            "destination": {
                "location": {
                    "latLng": {
                        "latitude": destination_lat,
                        "longitude": destination_lng,
                    }
                }
            },
            "travelMode": travel_mode,
            "computeAlternativeRoutes": True,
            "languageCode": "en-US",
            "units": "METRIC",
        }
        if travel_mode == "DRIVE":
            payload["routingPreference"] = "TRAFFIC_AWARE"
            payload["extraComputations"] = ["TRAFFIC_ON_POLYLINE"]
            payload["polylineQuality"] = "HIGH_QUALITY"

        try:
            with httpx.Client(timeout=12.0) as client:
                response = client.post(GOOGLE_ROUTES_API_URL, headers=headers, json=payload)
                data = response.json()
        except Exception:
            return None
        if response.status_code >= 400:
            return None

        routes = data.get("routes", [])
        if not routes:
            return None

        parsed_routes: list[list[dict]] = []
        route_meta: list[dict] = []
        for route_idx, route in enumerate(routes[:MAX_ROUTE_ALTERNATIVES]):
            route_segments: list[dict] = []
            total_route_distance_km = float(route.get("distanceMeters", 0.0)) / 1000.0
            legs = route.get("legs", [])
            encoded_overview = route.get("polyline", {}).get("encodedPolyline", "")
            overview_geometry = _decode_polyline(encoded_overview) if encoded_overview else []
            speed_intervals = (
                route.get("travelAdvisory", {}).get("speedReadingIntervals", [])
            )

            interval_parts: list[tuple[str, list[list[float]], float]] = []
            if len(overview_geometry) >= 2 and speed_intervals:
                for interval in speed_intervals:
                    start = int(interval.get("startPolylinePointIndex", 0))
                    end = int(
                        interval.get(
                            "endPolylinePointIndex",
                            len(overview_geometry),
                        )
                    )
                    start = max(0, min(start, len(overview_geometry) - 2))
                    end = max(start + 1, min(end, len(overview_geometry)))
                    geometry = overview_geometry[start : min(end + 1, len(overview_geometry))]
                    if len(geometry) < 2:
                        continue
                    traffic_speed = str(interval.get("speed", "NORMAL"))
                    interval_parts.append(
                        (
                            traffic_speed,
                            geometry,
                            max(_geometry_distance_km(geometry), 0.001),
                        )
                    )

            route_duration_seconds = _duration_seconds(route.get("duration"))
            if interval_parts and route_duration_seconds > 0:
                weighted_distance = sum(
                    distance
                    / GOOGLE_TRAFFIC_SPEED_FACTORS.get(traffic_speed, 1.0)
                    for traffic_speed, _, distance in interval_parts
                )
                normal_speed_kmph = max(
                    5.0,
                    min(
                        100.0,
                        weighted_distance * 3600.0 / route_duration_seconds,
                    ),
                )
                for interval_idx, (
                    traffic_speed,
                    geometry,
                    distance_km,
                ) in enumerate(interval_parts):
                    current_speed = max(
                        3.0,
                        normal_speed_kmph
                        * GOOGLE_TRAFFIC_SPEED_FACTORS.get(traffic_speed, 1.0),
                    )
                    traffic_level = GOOGLE_TRAFFIC_LEVELS.get(
                        traffic_speed,
                        "Low",
                    )
                    segment_id = (
                        f"GOOGLE-TRAFFIC-{route_idx}-{interval_idx}"
                    )
                    pred = traffic_predictor.predict_traffic(
                        segment_id,
                        distance_km,
                        departure_time,
                        coordinates=geometry,
                        previous_speed_kmph=current_speed,
                        traffic_level_override=traffic_level,
                    )
                    route_segments.append(
                        {
                            "segment_id": segment_id,
                            "from_node": f"Traffic zone {interval_idx + 1} (start)",
                            "to_node": f"Traffic zone {interval_idx + 1} (end)",
                            "distance_km": round(distance_km, 3),
                            "predicted_speed_kmph": pred.predicted_speed,
                            "predicted_travel_time_min": pred.predicted_travel_time,
                            "congestion_level": pred.traffic_level,
                            "coordinates": geometry,
                        }
                    )

            if not route_segments:
                for leg_idx, leg in enumerate(legs):
                    steps = leg.get("steps", [])
                    for step_idx, step in enumerate(steps):
                        encoded = step.get("polyline", {}).get("encodedPolyline", "")
                        geometry = _decode_polyline(encoded) if encoded else []
                        if len(geometry) < 2:
                            continue

                        distance_km = float(step.get("distanceMeters", 0.0)) / 1000.0
                        static_seconds = _duration_seconds(
                            step.get("staticDuration")
                        )
                        current_speed = (
                            distance_km / static_seconds * 3600.0
                            if static_seconds > 0
                            else None
                        )
                        segment_id = f"GOOGLE-ROUTES-{route_idx}-{leg_idx}-{step_idx}"
                        pred = traffic_predictor.predict_traffic(
                            segment_id,
                            max(distance_km, 0.02),
                            departure_time,
                            coordinates=geometry,
                            previous_speed_kmph=current_speed,
                        )

                        route_segments.append(
                            {
                                "segment_id": segment_id,
                                "from_node": f"Step {step_idx + 1} (start)",
                                "to_node": f"Step {step_idx + 1} (end)",
                                "distance_km": round(distance_km, 3),
                                "predicted_speed_kmph": pred.predicted_speed,
                                "predicted_travel_time_min": pred.predicted_travel_time,
                                "congestion_level": pred.traffic_level,
                                "coordinates": geometry,
                            }
                        )

            if not route_segments:
                geometry = overview_geometry
                if len(geometry) >= 2:
                    segment_id = f"GOOGLE-ROUTES-{route_idx}-overview"
                    pred = traffic_predictor.predict_traffic(
                        segment_id,
                        max(total_route_distance_km, 0.02),
                        departure_time,
                        coordinates=geometry,
                    )
                    route_segments.append(
                        {
                            "segment_id": segment_id,
                            "from_node": "Route (start)",
                            "to_node": "Route (end)",
                            "distance_km": round(total_route_distance_km, 3),
                            "predicted_speed_kmph": pred.predicted_speed,
                            "predicted_travel_time_min": pred.predicted_travel_time,
                            "congestion_level": pred.traffic_level,
                            "coordinates": geometry,
                        }
                    )

            if route_segments:
                parsed_routes.append(route_segments)
                route_meta.append({"route_idx": route_idx, "distance_km": total_route_distance_km})

        if not parsed_routes:
            return None

        shortest_i = min(range(len(parsed_routes)), key=lambda i: route_meta[i]["distance_km"])
        shortest_segments = parsed_routes[shortest_i]

        scored = sorted(
            ((i, *self._score_route(parsed_routes[i])) for i in range(len(parsed_routes))),
            key=lambda x: (x[1], x[2]),
        )
        best_i = scored[0][0]
        best_segments = parsed_routes[best_i]

        alternatives = []
        for i, segments in enumerate(parsed_routes):
            d_km, t_min = self._aggregate(segments)
            alternatives.append(
                {
                    "route_id": f"google_{i + 1}",
                    "total_distance_km": d_km,
                    "total_time_min": t_min,
                    "is_shortest": i == shortest_i,
                    "is_ai_optimal": i == best_i,
                    "segments": segments,
                }
            )

        return self._route_response(best_segments, shortest_segments, alternatives=alternatives)

    def _google_routes(
        self,
        source_lat: float,
        source_lng: float,
        destination_lat: float,
        destination_lng: float,
        departure_time: datetime,
        travel_mode: str,
    ) -> dict | None:
        if not GOOGLE_MAPS_API_KEY:
            return None

        params = {
            "origin": f"{source_lat},{source_lng}",
            "destination": f"{destination_lat},{destination_lng}",
            "mode": {
                "DRIVE": "driving",
                "WALK": "walking",
                "BICYCLE": "bicycling",
                "TRANSIT": "transit",
            }.get(travel_mode, "driving"),
            "alternatives": "true",
            "departure_time": "now",
            "key": GOOGLE_MAPS_API_KEY,
        }
        try:
            with httpx.Client(timeout=12.0) as client:
                response = client.get(GOOGLE_MAPS_DIRECTIONS_URL, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return None

        if payload.get("status") != "OK":
            return None

        routes = payload.get("routes", [])
        if not routes:
            return None

        parsed_routes: list[list[dict]] = []
        route_meta: list[dict] = []
        for route_idx, route in enumerate(routes[:MAX_ROUTE_ALTERNATIVES]):
            route_segments: list[dict] = []
            total_route_distance_km = 0.0

            for leg_idx, leg in enumerate(route.get("legs", [])):
                total_route_distance_km += float(leg.get("distance", {}).get("value", 0.0)) / 1000.0
                steps = leg.get("steps", [])
                for step_idx, step in enumerate(steps):
                    encoded = step.get("polyline", {}).get("points", "")
                    geometry = _decode_polyline(encoded) if encoded else []
                    if len(geometry) < 2:
                        continue

                    distance_km = float(step.get("distance", {}).get("value", 0.0)) / 1000.0
                    segment_id = f"GOOGLE-{route_idx}-{leg_idx}-{step_idx}"
                    pred = traffic_predictor.predict_traffic(
                        segment_id,
                        max(distance_km, 0.02),
                        departure_time,
                        coordinates=geometry,
                    )
                    name = step.get("html_instructions", "")
                    clean_name = (
                        name.replace("<b>", "").replace("</b>", "").replace("<div", " ").split("</div>")[0]
                    ) or f"Road {step_idx + 1}"

                    route_segments.append(
                        {
                            "segment_id": segment_id,
                            "from_node": f"{clean_name} (start)",
                            "to_node": f"{clean_name} (end)",
                            "distance_km": round(distance_km, 3),
                            "predicted_speed_kmph": pred.predicted_speed,
                            "predicted_travel_time_min": pred.predicted_travel_time,
                            "congestion_level": pred.traffic_level,
                            "coordinates": geometry,
                        }
                    )

            if route_segments:
                parsed_routes.append(route_segments)
                route_meta.append(
                    {
                        "route_idx": route_idx,
                        "distance_km": total_route_distance_km,
                    }
                )

        if not parsed_routes:
            return None

        shortest_i = min(range(len(parsed_routes)), key=lambda i: route_meta[i]["distance_km"])
        shortest_segments = parsed_routes[shortest_i]

        scored = sorted(
            ((i, *self._score_route(parsed_routes[i])) for i in range(len(parsed_routes))),
            key=lambda x: (x[1], x[2]),
        )
        best_i = scored[0][0]
        best_segments = parsed_routes[best_i]

        alternatives = []
        for i, segments in enumerate(parsed_routes):
            d_km, t_min = self._aggregate(segments)
            alternatives.append(
                {
                    "route_id": f"google_{i + 1}",
                    "total_distance_km": d_km,
                    "total_time_min": t_min,
                    "is_shortest": i == shortest_i,
                    "is_ai_optimal": i == best_i,
                    "segments": segments,
                }
            )

        return self._route_response(best_segments, shortest_segments, alternatives=alternatives)

    def _osrm_routes(
        self,
        source_lat: float,
        source_lng: float,
        destination_lat: float,
        destination_lng: float,
        departure_time: datetime,
    ) -> dict | None:
        url = (
            f"{OSRM_BASE_URL}/route/v1/driving/"
            f"{source_lng},{source_lat};{destination_lng},{destination_lat}"
        )
        params = {
            "alternatives": "true",
            "steps": "true",
            "overview": "full",
            "geometries": "geojson",
            "annotations": "false",
        }
        try:
            with httpx.Client(timeout=12.0) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return None

        routes = payload.get("routes", [])
        if not routes:
            return None

        parsed_routes: list[list[dict]] = []
        route_meta: list[dict] = []
        for route_idx, route in enumerate(routes[:MAX_ROUTE_ALTERNATIVES]):
            route_segments: list[dict] = []
            legs = route.get("legs", [])
            for leg_idx, leg in enumerate(legs):
                steps = leg.get("steps", [])
                for step_idx, step in enumerate(steps):
                    geometry = step.get("geometry", {}).get("coordinates", [])
                    if len(geometry) < 2:
                        continue
                    distance_km = float(step.get("distance", 0.0)) / 1000.0
                    segment_id = f"OSRM-{route_idx}-{leg_idx}-{step_idx}"
                    pred = traffic_predictor.predict_traffic(
                        segment_id,
                        max(distance_km, 0.02),
                        departure_time,
                        coordinates=geometry,
                    )
                    name = step.get("name") or f"Road {step_idx + 1}"
                    route_segments.append(
                        {
                            "segment_id": segment_id,
                            "from_node": f"{name} (start)",
                            "to_node": f"{name} (end)",
                            "distance_km": round(distance_km, 3),
                            "predicted_speed_kmph": pred.predicted_speed,
                            "predicted_travel_time_min": pred.predicted_travel_time,
                            "congestion_level": pred.traffic_level,
                            "coordinates": geometry,
                        }
                    )
            if not route_segments:
                route_geometry = route.get("geometry", {}).get("coordinates", [])
                if len(route_geometry) >= 2:
                    distance_km = float(route.get("distance", 0.0)) / 1000.0
                    segment_id = f"OSRM-OVERVIEW-{route_idx}"
                    pred = traffic_predictor.predict_traffic(
                        segment_id,
                        max(distance_km, 0.02),
                        departure_time,
                        coordinates=route_geometry,
                    )
                    route_segments.append(
                        {
                            "segment_id": segment_id,
                            "from_node": "OSRM route (start)",
                            "to_node": "OSRM route (end)",
                            "distance_km": round(distance_km, 3),
                            "predicted_speed_kmph": pred.predicted_speed,
                            "predicted_travel_time_min": pred.predicted_travel_time,
                            "congestion_level": pred.traffic_level,
                            "coordinates": route_geometry,
                        }
                    )
            if route_segments:
                parsed_routes.append(route_segments)
                route_meta.append(
                    {
                        "route_idx": route_idx,
                        "distance_km": float(route.get("distance", 0.0)) / 1000.0,
                        "duration_min": float(route.get("duration", 0.0)) / 60.0,
                    }
                )

        if not parsed_routes:
            return None

        # Shortest route by actual route distance from OSRM alternatives.
        shortest_i = min(range(len(parsed_routes)), key=lambda i: route_meta[i]["distance_km"])
        shortest_segments = parsed_routes[shortest_i]

        scored = sorted(
            ((i, *self._score_route(parsed_routes[i])) for i in range(len(parsed_routes))),
            key=lambda x: (x[1], x[2]),
        )
        best_i = scored[0][0]

        best_segments = parsed_routes[best_i]

        alternatives = []
        for i, segments in enumerate(parsed_routes):
            d_km, t_min = self._aggregate(segments)
            alternatives.append(
                {
                    "route_id": f"route_{i + 1}",
                    "total_distance_km": d_km,
                    "total_time_min": t_min,
                    "is_shortest": i == shortest_i,
                    "is_ai_optimal": i == best_i,
                    "segments": segments,
                }
            )

        return self._route_response(best_segments, shortest_segments, alternatives=alternatives)

    def _osrm_overview_route(
        self,
        source_lat: float,
        source_lng: float,
        destination_lat: float,
        destination_lng: float,
        departure_time: datetime,
    ) -> dict | None:
        url = (
            f"{OSRM_BASE_URL}/route/v1/driving/"
            f"{source_lng},{source_lat};{destination_lng},{destination_lat}"
        )
        params = {
            "alternatives": "false",
            "steps": "false",
            "overview": "full",
            "geometries": "geojson",
            "annotations": "false",
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return None

        routes = payload.get("routes", [])
        if not routes:
            return None

        route = routes[0]
        geometry = route.get("geometry", {}).get("coordinates", [])
        if len(geometry) < 2:
            return None

        distance_km = float(route.get("distance", 0.0)) / 1000.0
        segment_id = "OSRM-OVERVIEW-0"
        pred = traffic_predictor.predict_traffic(
            segment_id,
            max(distance_km, 0.02),
            departure_time,
            coordinates=geometry,
        )
        segment = {
            "segment_id": segment_id,
            "from_node": "OSRM route (start)",
            "to_node": "OSRM route (end)",
            "distance_km": round(distance_km, 3),
            "predicted_speed_kmph": pred.predicted_speed,
            "predicted_travel_time_min": pred.predicted_travel_time,
            "congestion_level": pred.traffic_level,
            "coordinates": geometry,
        }
        alternatives = [
            {
                "route_id": "osrm_1",
                "total_distance_km": round(distance_km, 2),
                "total_time_min": round(pred.predicted_travel_time, 2),
                "is_shortest": True,
                "is_ai_optimal": True,
                "segments": [segment],
            }
        ]
        return self._route_response([segment], [segment], alternatives=alternatives)

    def _path_to_segments(self, path: list[str], departure_time: datetime) -> list[dict]:
        segments = []
        for i in range(len(path) - 1):
            edge_data = self.base_graph.get_edge_data(path[i], path[i + 1])
            segment_id = edge_data["segment_id"]
            distance = float(edge_data["distance_km"])
            coordinates = edge_data.get("coordinates") or road_geometry_between_nodes(path[i], path[i + 1])
            pred = traffic_predictor.predict_traffic(
                segment_id,
                distance,
                departure_time,
                coordinates=coordinates,
            )
            segments.append(
                {
                    "segment_id": segment_id,
                    "from_node": path[i],
                    "to_node": path[i + 1],
                    "distance_km": round(distance, 2),
                    "predicted_speed_kmph": pred.predicted_speed,
                    "predicted_travel_time_min": pred.predicted_travel_time,
                    "congestion_level": pred.traffic_level,
                    "coordinates": coordinates,
                }
            )
        return segments

    def _graph_fallback(
        self,
        source_lat: float,
        source_lng: float,
        destination_lat: float,
        destination_lng: float,
        departure_time: datetime,
    ) -> dict:
        source_node = nearest_intersection(source_lat, source_lng)
        destination_node = nearest_intersection(destination_lat, destination_lng)
        try:
            candidate_paths = list(
                islice(
                    nx.shortest_simple_paths(
                        self.base_graph,
                        source=source_node,
                        target=destination_node,
                        weight="distance_km",
                    ),
                    MAX_ROUTE_ALTERNATIVES,
                )
            )
        except nx.NetworkXNoPath:
            return self.mock_route_fallback(source_lat, source_lng, destination_lat, destination_lng)
        if not candidate_paths:
            return self.mock_route_fallback(source_lat, source_lng, destination_lat, destination_lng)

        shortest_path = candidate_paths[0]
        scored_candidates: list[tuple[list[str], float, float]] = []
        for path in candidate_paths:
            segments = self._path_to_segments(path, departure_time)
            distance_km, total_time_min = self._aggregate(segments)
            scored_candidates.append((path, distance_km, total_time_min))
        scored_candidates.sort(key=lambda x: (x[2], x[1]))
        optimal_path = scored_candidates[0][0]

        shortest_segments = self._path_to_segments(shortest_path, departure_time)
        optimal_segments = self._path_to_segments(optimal_path, departure_time)
        shortest_segments = _anchor_segments_to_request(
            shortest_segments, source_lat, source_lng, destination_lat, destination_lng
        )
        optimal_segments = _anchor_segments_to_request(
            optimal_segments, source_lat, source_lng, destination_lat, destination_lng
        )
        alternatives = []
        for idx, path in enumerate(candidate_paths):
            segs = self._path_to_segments(path, departure_time)
            segs = _anchor_segments_to_request(
                segs, source_lat, source_lng, destination_lat, destination_lng
            )
            d_km, t_min = self._aggregate(segs)
            alternatives.append(
                {
                    "route_id": f"fallback_{idx + 1}",
                    "total_distance_km": d_km,
                    "total_time_min": t_min,
                    "is_shortest": idx == 0,
                    "is_ai_optimal": path == optimal_path,
                    "segments": segs,
                }
            )
        return self._route_response(optimal_segments, shortest_segments, alternatives=alternatives)

    def calculate_routes(
        self,
        source_lat: float,
        source_lng: float,
        destination_lat: float,
        destination_lng: float,
        departure_time: datetime,
        travel_mode: str = "TRANSIT",
    ) -> dict:
        corridor = [
            [source_lng, source_lat],
            [destination_lng, destination_lat],
        ]
        with traffic_predictor.live_context(corridor):
            google_routes_api_result = self._google_routes_api(
                source_lat,
                source_lng,
                destination_lat,
                destination_lng,
                departure_time,
                travel_mode,
            )
            if google_routes_api_result:
                return google_routes_api_result

            google_result = self._google_routes(
                source_lat,
                source_lng,
                destination_lat,
                destination_lng,
                departure_time,
                travel_mode,
            )
            if google_result:
                return google_result

            osrm_result = self._osrm_routes(
                source_lat,
                source_lng,
                destination_lat,
                destination_lng,
                departure_time,
            )
            if osrm_result:
                return osrm_result

            osrm_overview_result = self._osrm_overview_route(
                source_lat,
                source_lng,
                destination_lat,
                destination_lng,
                departure_time,
            )
            if osrm_overview_result:
                return osrm_overview_result

            return self._graph_fallback(
                source_lat,
                source_lng,
                destination_lat,
                destination_lng,
                departure_time,
            )

    @staticmethod
    def mock_route_fallback(
        source_lat: float, source_lng: float, destination_lat: float, destination_lng: float
    ) -> dict:
        common_segment = {
            "segment_id": "MOCK-1",
            "from_node": "SRC",
            "to_node": "DST",
            "distance_km": 12.4,
            "predicted_speed_kmph": 24.0,
            "predicted_travel_time_min": 31.0,
            "congestion_level": "Medium",
            "coordinates": [[source_lng, source_lat], [destination_lng, destination_lat]],
        }
        shortest_segment = {**common_segment, "segment_id": "MOCK-2", "predicted_travel_time_min": 35.0}
        return {
            "optimal_route": [common_segment],
            "shortest_route": [shortest_segment],
            "eta_minutes": 31.0,
            "distance_km": 12.4,
            "traffic_level": "Medium",
            "time_saved_minutes": 4.0,
            "comparison": [
                {
                    "route_name": "ai_optimal",
                    "segments": [common_segment],
                    "total_distance_km": 12.4,
                    "total_time_min": 31.0,
                },
                {
                    "route_name": "shortest",
                    "segments": [shortest_segment],
                    "total_distance_km": 12.4,
                    "total_time_min": 35.0,
                },
            ],
            "alternatives": [
                {
                    "route_id": "mock_1",
                    "total_distance_km": 12.4,
                    "total_time_min": 31.0,
                    "is_shortest": False,
                    "is_ai_optimal": True,
                    "segments": [common_segment],
                },
                {
                    "route_id": "mock_2",
                    "total_distance_km": 12.4,
                    "total_time_min": 35.0,
                    "is_shortest": True,
                    "is_ai_optimal": False,
                    "segments": [shortest_segment],
                },
            ],
        }


router_service = RouterService()
