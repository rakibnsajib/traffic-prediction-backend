from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "sample_dataset.csv"
MODEL_PATH = BASE_DIR / "traffic_model.pkl"
METRICS_PATH = BASE_DIR / "model_metrics.json"


def main() -> None:
    df = pd.read_csv(DATA_PATH)

    segment_encoder = LabelEncoder()
    df["road_segment_id_enc"] = segment_encoder.fit_transform(df["road_segment_id"])

    weather_map = {"clear": 0, "rain": 1, "fog": 2}
    df["weather_condition_enc"] = df["weather_condition"].map(weather_map).fillna(0).astype(int)

    features = [
        "hour",
        "day_of_week",
        "is_weekend",
        "previous_speed",
        "road_segment_id_enc",
        "weather_condition_enc",
    ]
    target = "predicted_speed"

    X = df[features].values
    y = df[target].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = RandomForestRegressor(n_estimators=220, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)
    preds = model.predict(X_test)

    mae = float(mean_absolute_error(y_test, preds))
    rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
    r2 = float(r2_score(y_test, preds))

    metrics = {
        "model": "RandomForestRegressor",
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "r2_score": round(r2, 4),
        "train_size": int(len(X_train)),
        "test_size": int(len(X_test)),
    }

    bundle = {
        "model": model,
        "encoder": segment_encoder,
        "weather_map": weather_map,
    }
    joblib.dump(bundle, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print("Training complete.")
    print(json.dumps(metrics, indent=2))
    print(f"Saved model to: {MODEL_PATH}")
    print(f"Saved metrics to: {METRICS_PATH}")


if __name__ == "__main__":
    main()

