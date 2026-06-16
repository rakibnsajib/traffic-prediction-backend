from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Coordinate(BaseModel):
    lat: float
    lng: float


class RouteRequest(BaseModel):
    source: Coordinate
    destination: Coordinate
    travel_mode: Literal["DRIVE", "WALK", "BICYCLE", "TRANSIT"] = "DRIVE"
    departure_time: datetime = Field(
        default_factory=datetime.utcnow,
        description="Optional ISO-8601 datetime string for departure. Defaults to current UTC time.",
    )


class PredictTrafficRequest(BaseModel):
    road_segment_id: str
    timestamp: datetime


class RouteSegment(BaseModel):
    segment_id: str
    from_node: str
    to_node: str
    distance_km: float
    predicted_speed_kmph: float
    predicted_travel_time_min: float
    congestion_level: Literal["Low", "Medium", "High"]
    coordinates: list[list[float]]


class RouteSummary(BaseModel):
    route_name: Literal["ai_optimal", "shortest"]
    segments: list[RouteSegment]
    total_distance_km: float
    total_time_min: float


class RouteResponse(BaseModel):
    optimal_route: list[RouteSegment]
    shortest_route: list[RouteSegment]
    eta_minutes: float
    distance_km: float
    traffic_level: Literal["Low", "Medium", "High"]
    time_saved_minutes: float
    comparison: list[RouteSummary]
    alternatives: list[dict]


class PredictTrafficResponse(BaseModel):
    road_segment_id: str
    predicted_speed: float
    predicted_travel_time: float
    traffic_level: Literal["Low", "Medium", "High"]
