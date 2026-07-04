from fastapi import APIRouter, HTTPException, status

from app.ml.model_service import traffic_predictor
from app.database.local_store import local_store
from app.models.schemas import (
    AuthResponse,
    LoginRequest,
    PredictTrafficRequest,
    PredictTrafficResponse,
    ProfileUpdateRequest,
    RouteRequest,
    RouteResponse,
    SignupRequest,
)
from app.routing.routing_service import router_service
from app.routing.graph_data import INTERSECTIONS, ROAD_SEGMENTS
from app.services.alert_service import alert_service
from app.services.geocode_service import geocode_service
from app.services.query_store import query_store


router = APIRouter(prefix="/api", tags=["Traffic"])


def _coordinates_for_segment(
    road_segment_id: str,
) -> list[list[float]] | None:
    segment = next(
        (
            item
            for item in ROAD_SEGMENTS
            if item["segment_id"] == road_segment_id
        ),
        None,
    )
    if not segment:
        return None
    start = INTERSECTIONS[segment["from_node"]]
    end = INTERSECTIONS[segment["to_node"]]
    return [
        [start["lng"], start["lat"]],
        [end["lng"], end["lat"]],
    ]


@router.post("/auth/login", response_model=AuthResponse)
def login(request: LoginRequest) -> dict:
    user = local_store.authenticate_user(request.email, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    return {"user": user}


@router.post("/auth/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(request: SignupRequest) -> dict:
    if len(request.password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters.")
    try:
        user = local_store.create_user(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"user": user}


@router.put("/auth/profile", response_model=AuthResponse)
def update_profile(request: ProfileUpdateRequest) -> dict:
    if request.password and len(request.password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters.")
    try:
        user = local_store.update_user_profile(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"user": user}


@router.post("/route", response_model=RouteResponse)
def get_route(request: RouteRequest) -> dict:
    result = router_service.calculate_routes(
        source_lat=request.source.lat,
        source_lng=request.source.lng,
        destination_lat=request.destination.lat,
        destination_lng=request.destination.lng,
        departure_time=request.departure_time,
        travel_mode=request.travel_mode,
    )
    query_store.add(request.model_dump(), result)
    alert_service.evaluate_route(result)
    return result


@router.post("/predict-traffic", response_model=PredictTrafficResponse)
def predict_traffic(request: PredictTrafficRequest) -> dict:
    distance_assumption_km = 1.4
    prediction = traffic_predictor.predict_traffic(
        road_segment_id=request.road_segment_id,
        distance_km=distance_assumption_km,
        timestamp=request.timestamp,
        coordinates=_coordinates_for_segment(request.road_segment_id),
    )
    alert_service.evaluate_prediction(
        road_segment_id=request.road_segment_id,
        traffic_level=prediction.traffic_level,
        predicted_travel_time=prediction.predicted_travel_time,
        predicted_speed=prediction.predicted_speed,
    )
    return {
        "road_segment_id": request.road_segment_id,
        "predicted_speed": prediction.predicted_speed,
        "predicted_travel_time": prediction.predicted_travel_time,
        "traffic_level": prediction.traffic_level,
    }


@router.get("/model-metrics")
def model_metrics() -> dict:
    return traffic_predictor.model_metrics()


@router.get("/sample-traffic-data")
def sample_traffic_data() -> dict:
    return {"records": traffic_predictor.sample_data(limit=50)}


@router.get("/recent-route-queries")
def recent_route_queries() -> dict:
    return {"records": query_store.latest(limit=15)}


@router.get("/alerts")
def alerts() -> dict:
    return {"records": alert_service.store.latest(limit=30)}


@router.get("/alerts/active")
def active_alerts() -> dict:
    return {"records": alert_service.store.active(limit=30)}


@router.get("/dashboard-reference-data")
def dashboard_reference_data() -> dict:
    return {
        "locations": local_store.list_bangladesh_locations(),
        "corridors": local_store.list_bangladesh_corridors(),
    }


@router.get("/geocode")
async def geocode_search(query: str) -> dict:
    records = await geocode_service.search(query=query, limit=6)
    return {"records": records}


@router.get("/reverse-geocode")
async def reverse_geocode(lat: float, lng: float) -> dict:
    record = await geocode_service.reverse(lat=lat, lng=lng)
    return {"record": record}
