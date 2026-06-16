from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.database.local_store import local_store


class InMemoryAlertStore:
    def __init__(self) -> None:
        self.alerts: list[dict[str, Any]] = []
        self._next_id = 1

    def _make_alert(
        self,
        severity: str,
        title: str,
        message: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "id": self._next_id,
            "severity": severity,
            "title": title,
            "message": message,
            "context": context,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def _is_duplicate_recent(self, title: str, context: dict[str, Any], minutes: int = 8) -> bool:
        if not self.alerts:
            return False
        source_segment = context.get("segment_id")
        now = datetime.now(timezone.utc)
        recent_cutoff = now - timedelta(minutes=minutes)
        for alert in reversed(self.alerts[-15:]):
            if alert.get("title") != title:
                continue
            created_at = alert.get("created_at")
            if not created_at:
                continue
            try:
                created = datetime.fromisoformat(created_at)
            except ValueError:
                continue
            if created < recent_cutoff:
                continue
            if source_segment and alert.get("context", {}).get("segment_id") == source_segment:
                return True
            if not source_segment:
                return True
        return False

    def create(
        self,
        severity: str,
        title: str,
        message: str,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        if self._is_duplicate_recent(title=title, context=context):
            return None
        alert = self._make_alert(
            severity=severity,
            title=title,
            message=message,
            context=context,
        )
        try:
            new_id = local_store.insert_alert(alert)
            alert["id"] = new_id
        except Exception:
            self.alerts.append(alert)
            self._next_id += 1
        return alert

    def latest(self, limit: int = 20) -> list[dict[str, Any]]:
        try:
            return local_store.list_alerts(limit=limit, active_only=False)
        except Exception:
            return self.alerts[-limit:][::-1]

    def active(self, limit: int = 20) -> list[dict[str, Any]]:
        try:
            return local_store.list_alerts(limit=limit, active_only=True)
        except Exception:
            records = [item for item in self.alerts if item.get("status") == "active"]
            return records[-limit:][::-1]


class AlertService:
    def __init__(self, store: InMemoryAlertStore) -> None:
        self.store = store

    def evaluate_route(self, route_result: dict[str, Any]) -> list[dict[str, Any]]:
        generated: list[dict[str, Any]] = []
        segments = route_result.get("optimal_route") or []
        if not segments:
            return generated

        high_segments = [seg for seg in segments if seg.get("congestion_level") == "High"]
        eta_minutes = float(route_result.get("eta_minutes") or 0)
        traffic_level = route_result.get("traffic_level", "Low")

        if traffic_level == "High" and eta_minutes >= 35:
            alert = self.store.create(
                severity="critical",
                title="Critical Congestion Corridor",
                message="Traffic is critically high and ETA crossed 35 minutes.",
                context={
                    "eta_minutes": eta_minutes,
                    "traffic_level": traffic_level,
                    "high_segments": len(high_segments),
                },
            )
            if alert:
                generated.append(alert)

        if len(high_segments) >= 2:
            primary_segment = high_segments[0]
            alert = self.store.create(
                severity="high",
                title="Multi-Segment High Congestion",
                message="Two or more route segments are in high congestion state.",
                context={
                    "segment_id": primary_segment.get("segment_id"),
                    "from_node": primary_segment.get("from_node"),
                    "to_node": primary_segment.get("to_node"),
                    "high_segments": len(high_segments),
                },
            )
            if alert:
                generated.append(alert)

        return generated

    def evaluate_prediction(
        self,
        road_segment_id: str,
        traffic_level: str,
        predicted_travel_time: float,
        predicted_speed: float,
    ) -> dict[str, Any] | None:
        if traffic_level != "High" or predicted_travel_time < 4.0:
            return None
        return self.store.create(
            severity="medium",
            title="Segment Alert",
            message="Segment shows high congestion for predicted timestamp.",
            context={
                "segment_id": road_segment_id,
                "predicted_travel_time": predicted_travel_time,
                "predicted_speed": predicted_speed,
            },
        )


alert_store = InMemoryAlertStore()
alert_service = AlertService(alert_store)