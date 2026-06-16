from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import hashlib
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


ML_DIR = Path(__file__).resolve().parents[2] / "ml"
MODEL_PATH = ML_DIR / "traffic_model.pkl"
METRICS_PATH = ML_DIR / "model_metrics.json"
SAMPLE_DATA_PATH = ML_DIR / "sample_dataset.csv"


@dataclass
class PredictionResult:
    predicted_speed: float
    predicted_travel_time: float
    traffic_level: str


def _traffic_level_from_speed(speed: float) -> str:
    if speed >= 35:
        return "Low"
    if speed >= 20:
        return "Medium"
    return "High"


class TrafficPredictor:
    def __init__(self) -> None:
        self.model_bundle = None
        if MODEL_PATH.exists():
            self.model_bundle = joblib.load(MODEL_PATH)
        self._fallback_mean_speed = 26.0
        self._segment_bias = {
            "R101": 1.0,
            "R102": -2.5,
            "R103": -1.0,
            "R104": -3.0,
            "R105": 0.5,
            "R106": -1.7,
            "R107": -2.0,
            "R108": 0.3,
            "R109": -0.4,
            "R110": 0.7,
        }
        self._segment_adjustment = {
            "R103": 2.5,
            "R104": 2.0,
            "R105": -4.5,
            "R106": -4.0,
        }

    @staticmethod
    def _dynamic_fallback_speed(
        road_segment_id: str,
        hour: int,
        is_weekend: int,
        base_speed: float,
    ) -> float:
        # Generate stable per-segment variation for unseen real-world road IDs.
        digest = hashlib.md5(road_segment_id.encode("utf-8")).hexdigest()
        road_factor = (int(digest[:2], 16) / 255.0) * 10.0 - 5.0  # -5..+5

        peak_penalty = 0.0
        if 7 <= hour <= 10 or 16 <= hour <= 20:
            peak_penalty = 6.0
        weekend_bonus = 2.0 if is_weekend else 0.0

        speed = base_speed + road_factor - peak_penalty + weekend_bonus
        return max(speed, 6.0)

    def predict_speed(self, road_segment_id: str, timestamp: datetime) -> float:
        hour = timestamp.hour
        day_of_week = timestamp.weekday()
        is_weekend = int(day_of_week >= 5)
        previous_speed = 25.0
        weather_condition = "clear"

        if self.model_bundle:
            model = self.model_bundle["model"]
            encoder = self.model_bundle["encoder"]
            weather_map = self.model_bundle.get(
                "weather_map", {"clear": 0, "rain": 1, "fog": 2}
            )
            if road_segment_id in getattr(encoder, "classes_", []):
                seg_encoded = encoder.transform([road_segment_id])[0]
                weather_encoded = weather_map.get(weather_condition, 0)
                X = np.array(
                    [[hour, day_of_week, is_weekend, previous_speed, seg_encoded, weather_encoded]]
                )
                speed = float(model.predict(X)[0])
                speed += self._segment_adjustment.get(road_segment_id, 0.0)
                return max(speed, 5.0)
            return self._dynamic_fallback_speed(
                road_segment_id=road_segment_id,
                hour=hour,
                is_weekend=is_weekend,
                base_speed=self._fallback_mean_speed,
            )

        speed = self._dynamic_fallback_speed(
            road_segment_id=road_segment_id,
            hour=hour,
            is_weekend=is_weekend,
            base_speed=(
                self._fallback_mean_speed
                + self._segment_bias.get(road_segment_id, 0.0)
                + self._segment_adjustment.get(road_segment_id, 0.0)
            ),
        )
        return speed

    def predict_traffic(
        self, road_segment_id: str, distance_km: float, timestamp: datetime
    ) -> PredictionResult:
        speed = self.predict_speed(road_segment_id, timestamp)
        travel_time = (distance_km / speed) * 60.0
        level = _traffic_level_from_speed(speed)
        return PredictionResult(
            predicted_speed=round(speed, 2),
            predicted_travel_time=round(travel_time, 2),
            traffic_level=level,
        )

    def model_metrics(self) -> dict:
        if METRICS_PATH.exists():
            return json.loads(METRICS_PATH.read_text(encoding="utf-8"))
        return {
            "model": "FallbackRuleBased",
            "mae": None,
            "rmse": None,
            "r2_score": None,
            "note": "Train model from backend with `python ml/train_model.py` to generate metrics.",
        }

    def sample_data(self, limit: int = 25) -> list[dict]:
        if SAMPLE_DATA_PATH.exists():
            df = pd.read_csv(SAMPLE_DATA_PATH)
            return df.head(limit).to_dict(orient="records")
        return []


traffic_predictor = TrafficPredictor()
