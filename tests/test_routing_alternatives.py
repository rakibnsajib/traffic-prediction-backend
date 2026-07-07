from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timezone

from app.routing import routing_service as routing_module


def _route_result(
    route_id: str,
    coordinates: list[list[float]],
    distance_km: float,
    time_min: float,
) -> dict:
    segment = {
        "segment_id": f"{route_id}-segment",
        "from_node": "start",
        "to_node": "end",
        "distance_km": distance_km,
        "predicted_speed_kmph": round(distance_km / time_min * 60.0, 2),
        "predicted_travel_time_min": time_min,
        "congestion_level": "Low",
        "coordinates": coordinates,
    }
    return {
        "optimal_route": [segment],
        "shortest_route": [segment],
        "eta_minutes": time_min,
        "distance_km": distance_km,
        "traffic_level": "Low",
        "time_saved_minutes": 0.0,
        "comparison": [],
        "alternatives": [
            {
                "route_id": route_id,
                "total_distance_km": distance_km,
                "total_time_min": time_min,
                "is_shortest": True,
                "is_ai_optimal": True,
                "segments": [segment],
            }
        ],
    }


def test_merge_route_results_removes_overlapping_provider_routes() -> None:
    service = routing_module.router_service
    google = _route_result(
        "google_1",
        [[90.3886, 23.8796], [90.3800, 23.8420], [90.3680, 23.8050]],
        10.8,
        13.0,
    )
    osrm_duplicate = _route_result(
        "osrm_1",
        [[90.3886, 23.8796], [90.3802, 23.8421], [90.3680, 23.8050]],
        10.9,
        13.2,
    )
    eastern_route = _route_result(
        "corridor_east_1",
        [[90.3886, 23.8796], [90.4100, 23.8420], [90.3680, 23.8050]],
        16.8,
        24.0,
    )

    merged = service._merge_route_results([google, osrm_duplicate, eastern_route])

    assert merged is not None
    assert len(merged["alternatives"]) == 2
    assert {route["route_id"] for route in merged["alternatives"]} == {
        "google_1",
        "corridor_east_1",
    }


def test_calculate_routes_adds_forced_corridors_when_providers_return_one(
    monkeypatch,
) -> None:
    service = routing_module.router_service
    source = (23.8796, 90.3886)
    destination = (23.8050, 90.3680)
    base_route = _route_result(
        "google_1",
        [[source[1], source[0]], [90.3800, 23.8420], [destination[1], destination[0]]],
        10.8,
        13.0,
    )
    osrm_duplicate = _route_result(
        "osrm_1",
        [[source[1], source[0]], [90.3802, 23.8421], [destination[1], destination[0]]],
        10.9,
        13.2,
    )
    forced_calls: list[str] = []

    monkeypatch.setattr(
        routing_module.traffic_predictor,
        "live_context",
        lambda _: nullcontext(),
    )
    monkeypatch.setattr(
        service,
        "_google_routes_api",
        lambda *args, **kwargs: base_route,
    )

    def fail_legacy_google(*args, **kwargs):
        raise AssertionError("Legacy Google routing should not run after Routes API succeeds.")

    monkeypatch.setattr(service, "_google_routes", fail_legacy_google)

    def fake_osrm(
        source_lat,
        source_lng,
        destination_lat,
        destination_lng,
        departure_time,
        waypoints=None,
        alternatives=routing_module.TARGET_ROUTE_ALTERNATIVES,
        route_id_prefix="osrm",
        timeout_seconds=12.0,
    ):
        _ = (
            source_lat,
            source_lng,
            destination_lat,
            destination_lng,
            departure_time,
            alternatives,
            timeout_seconds,
        )
        if not waypoints:
            return osrm_duplicate

        forced_calls.append(route_id_prefix)
        waypoint_lat, waypoint_lng = waypoints[0]
        if waypoint_lng < (source[1] + destination[1]) / 2:
            return _route_result(
                route_id_prefix,
                [
                    [source[1], source[0]],
                    [waypoint_lng, waypoint_lat],
                    [destination[1], destination[0]],
                ],
                11.3,
                14.0,
            )
        return _route_result(
            route_id_prefix,
            [
                [source[1], source[0]],
                [waypoint_lng, waypoint_lat],
                [destination[1], destination[0]],
            ],
            17.1,
            25.0,
        )

    monkeypatch.setattr(service, "_osrm_routes", fake_osrm)

    result = service.calculate_routes(
        source_lat=source[0],
        source_lng=source[1],
        destination_lat=destination[0],
        destination_lng=destination[1],
        departure_time=datetime.now(timezone.utc),
        travel_mode="DRIVE",
    )

    assert len(result["alternatives"]) == 3
    assert set(forced_calls) == {"corridor_west", "corridor_east"}
    assert sum(route["is_shortest"] for route in result["alternatives"]) == 1
    assert sum(route["is_ai_optimal"] for route in result["alternatives"]) == 1
