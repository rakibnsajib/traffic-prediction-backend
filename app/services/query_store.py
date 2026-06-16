from datetime import datetime, timezone
from typing import Any

from app.database.local_store import local_store


class InMemoryQueryStore:
    def __init__(self) -> None:
        self.route_queries: list[dict[str, Any]] = []

    def add(self, payload: dict[str, Any], result: dict[str, Any]) -> None:
        departure_value = payload.get("departure_time")
        record = {
            "source": payload["source"],
            "destination": payload["destination"],
            "departure_time": departure_value.isoformat()
            if isinstance(departure_value, datetime)
            else departure_value,
            "eta_minutes": result.get("eta_minutes"),
            "distance_km": result.get("distance_km"),
            "traffic_level": result.get("traffic_level"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.route_queries.append(record)
        try:
            local_store.insert_route_query(record)
        except Exception:
            # Keep API functional even when local persistence is unavailable.
            return

    def latest(self, limit: int = 10) -> list[dict[str, Any]]:
        try:
            return local_store.list_route_queries(limit=limit)
        except Exception:
            return self.route_queries[-limit:]


query_store = InMemoryQueryStore()
