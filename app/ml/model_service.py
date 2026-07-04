from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

import joblib
import pandas as pd

from app.services.tomtom_traffic_service import tomtom_traffic_service
from app.services.weather_service import weather_service


ML_DIR = Path(__file__).resolve().parents[2] / "ml"
MODEL_PATH = ML_DIR / "traffic_model.pkl"
METRICS_PATH = ML_DIR / "model_metrics.json"
PREVIEW_PATH = ML_DIR / "real_dataset_preview.csv"


@dataclass
class PredictionResult:
    predicted_speed: float
    predicted_travel_time: float
    traffic_level: str


@dataclass(frozen=True)
class LivePredictionInputs:
    previous_speed_kmph: float | None
    weather: object | None


_live_inputs: ContextVar[LivePredictionInputs | None] = ContextVar(
    "traffic_live_inputs",
    default=None,
)


def _traffic_level_from_speed(speed: float) -> str:
    if speed >= 35:
        return "Low"
    if speed >= 20:
        return "Medium"
    return "High"


class TrafficPredictor:
    def __init__(self) -> None:
        self.model_bundle = (
            joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None
        )

    @contextmanager
    def live_context(
        self,
        coordinates: list[list[float]] | None,
    ):
        """Fetch live corridor inputs once and reuse them for all route segments."""
        with ThreadPoolExecutor(max_workers=2) as executor:
            speed_future = executor.submit(
                tomtom_traffic_service.current_speed_kmph,
                coordinates,
            )
            weather_future = executor.submit(
                weather_service.current_weather,
                coordinates,
            )
            previous_speed = speed_future.result()
            weather = weather_future.result()
        inputs = LivePredictionInputs(
            previous_speed_kmph=previous_speed,
            weather=weather,
        )
        token = _live_inputs.set(inputs)
        try:
            yield
        finally:
            _live_inputs.reset(token)

    def _feature_row(
        self,
        timestamp: datetime,
        coordinates: list[list[float]] | None,
        previous_speed_kmph: float | None = None,
    ) -> dict[str, float | int]:
        bundle = self.model_bundle or {}
        weather_defaults = bundle.get("weather_defaults", {})
        live_inputs = _live_inputs.get()
        previous_speed = previous_speed_kmph
        if previous_speed is None:
            previous_speed = (
                live_inputs.previous_speed_kmph
                if live_inputs is not None
                else tomtom_traffic_service.current_speed_kmph(coordinates)
            )
        if previous_speed is None:
            previous_speed = float(
                bundle.get("default_previous_speed_kmph", 40.0)
            )

        weather = (
            live_inputs.weather
            if live_inputs is not None
            else weather_service.current_weather(coordinates)
        )
        if weather is None:
            temperature_c = float(
                weather_defaults.get("temperature_c", 20.0)
            )
            relative_humidity = float(
                weather_defaults.get("relative_humidity", 60.0)
            )
            precipitation_mm = float(
                weather_defaults.get("precipitation_mm", 0.0)
            )
            wind_speed_kmph = float(
                weather_defaults.get("wind_speed_kmph", 5.0)
            )
            is_rain = int(weather_defaults.get("is_rain", 0))
            is_fog = int(weather_defaults.get("is_fog", 0))
            is_cloudy = int(weather_defaults.get("is_cloudy", 0))
        else:
            temperature_c = weather.temperature_c
            relative_humidity = weather.relative_humidity
            precipitation_mm = weather.precipitation_mm
            wind_speed_kmph = weather.wind_speed_kmph
            is_rain = weather.is_rain
            is_fog = weather.is_fog
            is_cloudy = weather.is_cloudy

        return {
            "hour": timestamp.hour,
            "day_of_week": timestamp.weekday(),
            "is_weekend": int(timestamp.weekday() >= 5),
            "previous_speed_kmph": previous_speed,
            "temperature_c": temperature_c,
            "relative_humidity": relative_humidity,
            "precipitation_mm": precipitation_mm,
            "wind_speed_kmph": wind_speed_kmph,
            "is_rain": is_rain,
            "is_fog": is_fog,
            "is_cloudy": is_cloudy,
        }

    def predict_speed(
        self,
        road_segment_id: str,
        timestamp: datetime,
        coordinates: list[list[float]] | None = None,
        previous_speed_kmph: float | None = None,
    ) -> float:
        _ = road_segment_id
        row = self._feature_row(
            timestamp,
            coordinates,
            previous_speed_kmph=previous_speed_kmph,
        )
        if not self.model_bundle:
            return max(float(row["previous_speed_kmph"]), 5.0)

        feature_names = self.model_bundle["feature_names"]
        features = pd.DataFrame([row], columns=feature_names)
        model_output = float(
            self.model_bundle["model"].predict(features)[0]
        )
        speed = (
            float(row["previous_speed_kmph"]) + model_output
            if self.model_bundle.get("target_type") == "speed_delta"
            else model_output
        )

        # Keep only physical road-speed bounds. Training-quantile clipping
        # would incorrectly force congested Dhaka speeds up to the minimum
        # observed on the Los Angeles freeway training corridor.
        lower = 3.0
        upper = 130.0
        return min(max(speed, lower), upper)

    def predict_traffic(
        self,
        road_segment_id: str,
        distance_km: float,
        timestamp: datetime,
        coordinates: list[list[float]] | None = None,
        previous_speed_kmph: float | None = None,
        traffic_level_override: str | None = None,
    ) -> PredictionResult:
        speed = self.predict_speed(
            road_segment_id,
            timestamp,
            coordinates,
            previous_speed_kmph=previous_speed_kmph,
        )
        travel_time = (distance_km / speed) * 60.0
        level = traffic_level_override or _traffic_level_from_speed(speed)
        return PredictionResult(
            predicted_speed=round(speed, 2),
            predicted_travel_time=round(travel_time, 2),
            traffic_level=level,
        )

    def model_metrics(self) -> dict:
        if METRICS_PATH.exists():
            return json.loads(METRICS_PATH.read_text(encoding="utf-8"))
        return {
            "model": "LiveSpeedFallback",
            "mae": None,
            "rmse": None,
            "r2_score": None,
            "note": "Run `python ml/train_model.py` from backend.",
        }

    def sample_data(self, limit: int = 25) -> list[dict]:
        if not PREVIEW_PATH.exists():
            return []
        data = pd.read_csv(PREVIEW_PATH).head(limit)
        return data.where(pd.notna(data), None).to_dict(orient="records")


traffic_predictor = TrafficPredictor()
