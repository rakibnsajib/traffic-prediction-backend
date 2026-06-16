from __future__ import annotations

from datetime import datetime
from pathlib import Path

import joblib
import numpy as np


BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "traffic_model.pkl"


def predict_speed(road_segment_id: str, timestamp_iso: str) -> float:
    bundle = joblib.load(MODEL_PATH)
    model = bundle["model"]
    encoder = bundle["encoder"]
    weather_map = bundle["weather_map"]

    timestamp = datetime.fromisoformat(timestamp_iso)
    hour = timestamp.hour
    day_of_week = timestamp.weekday()
    is_weekend = int(day_of_week >= 5)
    previous_speed = 25.0
    weather_condition = weather_map["clear"]

    segment_encoded = encoder.transform([road_segment_id])[0]
    X = np.array(
        [[hour, day_of_week, is_weekend, previous_speed, segment_encoded, weather_condition]]
    )
    pred = float(model.predict(X)[0])
    return round(max(pred, 5.0), 2)


if __name__ == "__main__":
    segment_id = "R102"
    ts = "2026-04-25T09:00:00"
    speed = predict_speed(segment_id, ts)
    print(f"Predicted speed for {segment_id} at {ts}: {speed} km/h")

