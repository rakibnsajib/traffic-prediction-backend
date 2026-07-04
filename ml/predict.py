from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

import joblib
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "traffic_model.pkl"


def predict_speed(
    timestamp_iso: str,
    previous_speed_kmph: float,
    temperature_c: float,
    relative_humidity: float,
    precipitation_mm: float,
    wind_speed_kmph: float,
    is_rain: int = 0,
    is_fog: int = 0,
    is_cloudy: int = 0,
) -> float:
    bundle = joblib.load(MODEL_PATH)
    timestamp = datetime.fromisoformat(timestamp_iso)
    row = {
        "hour": timestamp.hour,
        "day_of_week": timestamp.weekday(),
        "is_weekend": int(timestamp.weekday() >= 5),
        "previous_speed_kmph": previous_speed_kmph,
        "temperature_c": temperature_c,
        "relative_humidity": relative_humidity,
        "precipitation_mm": precipitation_mm,
        "wind_speed_kmph": wind_speed_kmph,
        "is_rain": is_rain,
        "is_fog": is_fog,
        "is_cloudy": is_cloudy,
    }
    features = pd.DataFrame([row], columns=bundle["feature_names"])
    model_output = float(bundle["model"].predict(features)[0])
    prediction = (
        previous_speed_kmph + model_output
        if bundle.get("target_type") == "speed_delta"
        else model_output
    )
    return round(max(prediction, 3.0), 2)


if __name__ == "__main__":
    speed = predict_speed(
        timestamp_iso="2026-06-20T09:00:00",
        previous_speed_kmph=25.0,
        temperature_c=30.0,
        relative_humidity=75.0,
        precipitation_mm=0.0,
        wind_speed_kmph=8.0,
        is_cloudy=1,
    )
    print(f"Predicted speed in 15 minutes: {speed} km/h")
