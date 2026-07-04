from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.services.alert_service import alert_service


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_route_endpoint_persists_and_returns_payload(monkeypatch) -> None:
    from app.api import routes

    def fake_calculate_routes(**_: object) -> dict:
        return {
            "optimal_route": [
                {
                    "segment_id": "T-001",
                    "from_node": "A",
                    "to_node": "B",
                    "distance_km": 1.2,
                    "predicted_speed_kmph": 14.0,
                    "predicted_travel_time_min": 5.1,
                    "congestion_level": "High",
                    "coordinates": [[90.4, 23.8], [90.39, 23.79]],
                },
                {
                    "segment_id": "T-002",
                    "from_node": "B",
                    "to_node": "C",
                    "distance_km": 1.3,
                    "predicted_speed_kmph": 12.0,
                    "predicted_travel_time_min": 6.0,
                    "congestion_level": "High",
                    "coordinates": [[90.39, 23.79], [90.37, 23.78]],
                },
            ],
            "shortest_route": [
                {
                    "segment_id": "S-001",
                    "from_node": "A",
                    "to_node": "C",
                    "distance_km": 2.0,
                    "predicted_speed_kmph": 20.0,
                    "predicted_travel_time_min": 6.2,
                    "congestion_level": "Medium",
                    "coordinates": [[90.4, 23.8], [90.37, 23.78]],
                }
            ],
            "eta_minutes": 41.3,
            "distance_km": 2.5,
            "traffic_level": "High",
            "time_saved_minutes": 3.2,
            "comparison": [],
            "alternatives": [],
        }

    monkeypatch.setattr(routes.router_service, "calculate_routes", fake_calculate_routes)

    payload = {
        "source": {"lat": 23.8103, "lng": 90.4125},
        "destination": {"lat": 23.7806, "lng": 90.2794},
        "departure_time": datetime.now(timezone.utc).isoformat(),
    }
    response = client.post("/api/route", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["traffic_level"] == "High"
    assert "optimal_route" in body


def test_predict_traffic_and_active_alerts(monkeypatch) -> None:
    from app.api import routes
    from app.ml.model_service import PredictionResult

    def fake_predict_traffic(
        road_segment_id: str,
        distance_km: float,
        timestamp: datetime,
        coordinates: list[list[float]] | None = None,
    ) -> PredictionResult:
        _ = (road_segment_id, distance_km, timestamp, coordinates)
        return PredictionResult(
            predicted_speed=8.5,
            predicted_travel_time=5.5,
            traffic_level="High",
        )

    monkeypatch.setattr(routes.traffic_predictor, "predict_traffic", fake_predict_traffic)

    predict_resp = client.post(
        "/api/predict-traffic",
        json={"road_segment_id": "R102", "timestamp": datetime.now(timezone.utc).isoformat()},
    )
    assert predict_resp.status_code == 200
    predict_data = predict_resp.json()
    assert predict_data["traffic_level"] == "High"

    alerts_resp = client.get("/api/alerts/active")
    assert alerts_resp.status_code == 200
    alerts_data = alerts_resp.json()["records"]
    assert isinstance(alerts_data, list)
    assert any(item.get("title") in {"Segment Alert", "Multi-Segment High Congestion", "Critical Congestion Corridor"} for item in alerts_data)


def test_route_request_validation_error() -> None:
    response = client.post(
        "/api/route",
        json={"source": {"lat": 12.2}, "destination": {"lat": 22.0, "lng": 90.1}},
    )
    assert response.status_code == 422
