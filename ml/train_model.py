from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "real_data" / "traffic_weather_full2020.csv"
MODEL_PATH = BASE_DIR / "traffic_model.pkl"
METRICS_PATH = BASE_DIR / "model_metrics.json"
PREVIEW_PATH = BASE_DIR / "real_dataset_preview.csv"

FORECAST_HORIZON_MINUTES = 15
FORECAST_STEPS = FORECAST_HORIZON_MINUTES // 5
MPH_TO_KMPH = 1.609344

FEATURE_NAMES = [
    "hour",
    "day_of_week",
    "is_weekend",
    "previous_speed_kmph",
    "temperature_c",
    "relative_humidity",
    "precipitation_mm",
    "wind_speed_kmph",
    "is_rain",
    "is_fog",
    "is_cloudy",
]

def _temperature_f_to_c(series: pd.Series) -> pd.Series:
    fahrenheit = pd.to_numeric(
        series.astype(str).str.extract(r"(-?\d+(?:\.\d+)?)")[0],
        errors="coerce",
    )
    return (fahrenheit - 32.0) * (5.0 / 9.0)


def _weather_flags(condition: pd.Series) -> pd.DataFrame:
    normalized = condition.fillna("").astype(str).str.lower()
    is_rain = normalized.str.contains(
        r"rain|thunder|shower|drizzle", regex=True
    ).astype(int)
    is_fog = normalized.str.contains(r"fog|mist", regex=True).astype(int)
    is_cloudy = normalized.str.contains(
        r"cloud|overcast|haze|dust", regex=True
    ).astype(int)
    return pd.DataFrame(
        {
            "is_rain": is_rain,
            "is_fog": is_fog,
            "is_cloudy": ((is_cloudy + is_rain + is_fog) > 0).astype(int),
        }
    )


def prepare_training_data(raw: pd.DataFrame) -> pd.DataFrame:
    timestamp = pd.to_datetime(raw["5 Minutes"], errors="coerce")
    speed_mph = pd.to_numeric(raw["(mph)"], errors="coerce")
    flags = _weather_flags(raw["Condition"])

    data = pd.DataFrame(
        {
            "timestamp": timestamp,
            "hour": timestamp.dt.hour,
            "day_of_week": timestamp.dt.dayofweek,
            "is_weekend": (timestamp.dt.dayofweek >= 5).astype(int),
            "previous_speed_kmph": speed_mph * MPH_TO_KMPH,
            "temperature_c": _temperature_f_to_c(raw["Temperature"]),
            "relative_humidity": pd.to_numeric(
                raw["Humidity"], errors="coerce"
            ),
            "precipitation_mm": pd.to_numeric(
                raw["Precip."], errors="coerce"
            )
            * 25.4,
            "wind_speed_kmph": pd.to_numeric(
                raw["Wind Speed"], errors="coerce"
            )
            * MPH_TO_KMPH,
            "condition": raw["Condition"].fillna("Unknown").astype(str),
            **{column: flags[column] for column in flags.columns},
        }
    )
    data["target_timestamp"] = data["timestamp"].shift(-FORECAST_STEPS)
    data["predicted_speed_kmph"] = data["previous_speed_kmph"].shift(
        -FORECAST_STEPS
    )

    expected_delta = pd.Timedelta(minutes=FORECAST_HORIZON_MINUTES)
    data = data[
        (data["target_timestamp"] - data["timestamp"]) == expected_delta
    ]
    data = data.dropna(
        subset=FEATURE_NAMES + ["predicted_speed_kmph"]
    ).reset_index(drop=True)
    return data


def main() -> None:
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Real dataset not found at {DATA_PATH}. "
            "Download the Kaggle PeMS traffic-weather dataset first."
        )

    raw = pd.read_csv(DATA_PATH, low_memory=False)
    data = prepare_training_data(raw)
    if len(data) < 1000:
        raise ValueError("Not enough valid real observations to train the model.")

    split_index = int(len(data) * 0.8)
    train = data.iloc[:split_index]
    test = data.iloc[split_index:]
    X_train = train[FEATURE_NAMES]
    y_train = (
        train["predicted_speed_kmph"]
        - train["previous_speed_kmph"]
    )
    X_test = test[FEATURE_NAMES]
    y_test = test["predicted_speed_kmph"]

    model = XGBRegressor(
        n_estimators=500,
        max_depth=5,
        learning_rate=0.04,
        subsample=0.85,
        colsample_bytree=0.85,
        objective="reg:squarederror",
        n_jobs=4,
        random_state=42,
    )
    model.fit(X_train, y_train)
    persistence_predictions = X_test["previous_speed_kmph"].to_numpy()
    predictions = persistence_predictions + model.predict(X_test)

    mae = float(mean_absolute_error(y_test, predictions))
    rmse = float(np.sqrt(mean_squared_error(y_test, predictions)))
    r2 = float(r2_score(y_test, predictions))
    persistence_mae = float(
        mean_absolute_error(y_test, persistence_predictions)
    )

    defaults = {
        feature: float(data[feature].median())
        for feature in FEATURE_NAMES
        if feature
        not in {"hour", "day_of_week", "is_weekend", "previous_speed_kmph"}
    }
    metrics = {
        "model": "XGBRegressor",
        "target": "15-minute speed change",
        "dataset": "US Traffic Data with Weather and Calendar (PeMS)",
        "dataset_source": (
            "https://www.kaggle.com/datasets/maryamshoaei/"
            "us-traffic-data-with-weather-and-calendar-dataset"
        ),
        "forecast_horizon_minutes": FORECAST_HORIZON_MINUTES,
        "speed_unit": "km/h",
        "split": "chronological 80/20",
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "r2_score": round(r2, 4),
        "persistence_baseline_mae": round(persistence_mae, 4),
        "train_size": int(len(train)),
        "test_size": int(len(test)),
        "total_valid_rows": int(len(data)),
        "training_period_start": data["timestamp"].min().isoformat(),
        "training_period_end": data["timestamp"].max().isoformat(),
    }

    bundle = {
        "model": model,
        "target_type": "speed_delta",
        "feature_names": FEATURE_NAMES,
        "forecast_horizon_minutes": FORECAST_HORIZON_MINUTES,
        "speed_unit": "km/h",
        "default_previous_speed_kmph": float(
            data["previous_speed_kmph"].median()
        ),
        "weather_defaults": defaults,
        "training_speed_min_kmph": float(
            data["predicted_speed_kmph"].quantile(0.001)
        ),
        "training_speed_max_kmph": float(
            data["predicted_speed_kmph"].quantile(0.999)
        ),
        "dataset_source": metrics["dataset_source"],
    }
    joblib.dump(bundle, MODEL_PATH)
    METRICS_PATH.write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8",
    )

    preview = data[
        [
            "timestamp",
            "hour",
            "day_of_week",
            "is_weekend",
            "previous_speed_kmph",
            "condition",
            "temperature_c",
            "relative_humidity",
            "precipitation_mm",
            "wind_speed_kmph",
            "predicted_speed_kmph",
        ]
    ].head(100).copy()
    preview["previous_speed"] = preview["previous_speed_kmph"].round(2)
    preview["road_segment_id"] = "PEMS-VENTURA-EB"
    preview["weather_condition"] = preview["condition"]
    preview["predicted_speed"] = preview["predicted_speed_kmph"].round(2)
    preview.to_csv(PREVIEW_PATH, index=False)

    print("Training complete.")
    print(json.dumps(metrics, indent=2))
    print(f"Saved model to: {MODEL_PATH}")
    print(f"Saved preview to: {PREVIEW_PATH}")


if __name__ == "__main__":
    main()
