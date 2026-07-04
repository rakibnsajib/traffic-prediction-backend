from __future__ import annotations

import math
import os
from pathlib import Path
from time import perf_counter
from typing import Callable

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.ensemble import (
    ExtraTreesRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "real_data" / "traffic_weather_full2020.csv"
RESULTS_PATH = BASE_DIR / "time_series_model_benchmark.md"
FORECAST_STEPS = 3
FORECAST_MINUTES = 15
MPH_TO_KMPH = 1.609344
RANDOM_SEED = 42

FEATURES = [
    "speed_t",
    "speed_lag_5m",
    "speed_lag_10m",
    "speed_lag_15m",
    "speed_lag_30m",
    "speed_lag_60m",
    "speed_mean_15m",
    "speed_mean_30m",
    "speed_std_30m",
    "flow_t",
    "flow_lag_15m",
    "flow_mean_30m",
    "hour_sin",
    "hour_cos",
    "week_sin",
    "week_cos",
    "is_weekend",
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


def prepare_data(raw: pd.DataFrame) -> pd.DataFrame:
    timestamp = pd.to_datetime(raw["5 Minutes"], errors="coerce")
    condition = raw["Condition"].fillna("").astype(str).str.lower()
    speed = pd.to_numeric(raw["(mph)"], errors="coerce") * MPH_TO_KMPH
    flow = pd.to_numeric(raw["Flow"], errors="coerce")
    data = pd.DataFrame(
        {
            "timestamp": timestamp,
            "speed_t": speed,
            "flow_t": flow,
            "temperature_c": _temperature_f_to_c(raw["Temperature"]),
            "relative_humidity": pd.to_numeric(raw["Humidity"], errors="coerce"),
            "precipitation_mm": (
                pd.to_numeric(raw["Precip."], errors="coerce") * 25.4
            ),
            "wind_speed_kmph": (
                pd.to_numeric(raw["Wind Speed"], errors="coerce") * MPH_TO_KMPH
            ),
            "is_rain": condition.str.contains(
                r"rain|thunder|shower|drizzle", regex=True
            ).astype(int),
            "is_fog": condition.str.contains(r"fog|mist", regex=True).astype(int),
            "is_cloudy": condition.str.contains(
                r"cloud|overcast|haze|dust|rain|thunder|fog|mist",
                regex=True,
            ).astype(int),
        }
    )
    hour = timestamp.dt.hour + timestamp.dt.minute / 60.0
    weekday = timestamp.dt.dayofweek
    data["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    data["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    data["week_sin"] = np.sin(2 * np.pi * weekday / 7)
    data["week_cos"] = np.cos(2 * np.pi * weekday / 7)
    data["is_weekend"] = (weekday >= 5).astype(int)

    for minutes in (5, 10, 15, 30, 60):
        data[f"speed_lag_{minutes}m"] = speed.shift(minutes // 5)
    data["speed_mean_15m"] = speed.rolling(3).mean()
    data["speed_mean_30m"] = speed.rolling(6).mean()
    data["speed_std_30m"] = speed.rolling(6).std()
    data["flow_lag_15m"] = flow.shift(3)
    data["flow_mean_30m"] = flow.rolling(6).mean()
    data["target_speed_kmph"] = speed.shift(-FORECAST_STEPS)
    data["target_timestamp"] = timestamp.shift(-FORECAST_STEPS)

    valid_horizon = (
        data["target_timestamp"] - data["timestamp"]
        == pd.Timedelta(minutes=FORECAST_MINUTES)
    )
    return data.loc[valid_horizon].dropna().reset_index(drop=True)


def evaluate(y_true: np.ndarray, predictions: np.ndarray) -> dict[str, float]:
    return {
        "mae": round(float(mean_absolute_error(y_true, predictions)), 4),
        "rmse": round(
            float(math.sqrt(mean_squared_error(y_true, predictions))),
            4,
        ),
        "r2_score": round(float(r2_score(y_true, predictions)), 4),
    }


def run_model(
    name: str,
    factory: Callable[[], object],
    X_train: pd.DataFrame,
    y_train_delta: pd.Series,
    X_test: pd.DataFrame,
    y_test: np.ndarray,
) -> dict:
    started = perf_counter()
    model = factory()
    model.fit(X_train, y_train_delta)
    training_seconds = perf_counter() - started
    started = perf_counter()
    predictions = X_test["speed_t"].to_numpy() + model.predict(X_test)
    prediction_seconds = perf_counter() - started
    return {
        "model": name,
        **evaluate(y_test, predictions),
        "training_seconds": round(training_seconds, 3),
        "prediction_seconds": round(prediction_seconds, 3),
    }


def markdown_report(
    results: list[dict],
    train_size: int,
    test_size: int,
) -> str:
    ranked = sorted(results, key=lambda result: result["mae"])
    rows = "\n".join(
        (
            f"| {index} | {result['model']} | {result['mae']:.4f} | "
            f"{result['rmse']:.4f} | {result['r2_score']:.4f} |"
        )
        for index, result in enumerate(ranked, start=1)
    )
    return f"""# Time-Series Model Benchmark

## Setup

- Dataset: US Traffic Data with Weather and Calendar (PeMS)
- Forecast horizon: {FORECAST_MINUTES} minutes
- Split: chronological 80/20
- Training rows: {train_size}
- Test rows: {test_size}
- Features: current speed/flow, 5–60 minute lags, rolling statistics, time, and weather
- Ranking metric: lowest MAE

## Results

| Rank | Model | MAE (km/h) | RMSE (km/h) | R² |
|---:|---|---:|---:|---:|
{rows}

## Conclusion

**Best benchmark model: {ranked[0]['model']}**, with MAE
`{ranked[0]['mae']:.4f} km/h`.

XGBoost is selected for the production model. The benchmark uses historical lag
and rolling features; the live production model uses only inputs available at
request time, so its production metrics are reported separately in
`model_metrics.json`.
"""


def main() -> None:
    data = prepare_data(pd.read_csv(DATA_PATH, low_memory=False))
    split_index = int(len(data) * 0.8)
    train = data.iloc[:split_index]
    test = data.iloc[split_index:]
    X_train = train[FEATURES]
    X_test = test[FEATURES]
    y_train_delta = train["target_speed_kmph"] - train["speed_t"]
    y_test = test["target_speed_kmph"].to_numpy()

    results: list[dict] = []
    models: list[tuple[str, Callable[[], object]]] = [
        (
            "HistGradientBoosting",
            lambda: HistGradientBoostingRegressor(
                max_iter=300,
                learning_rate=0.05,
                l2_regularization=2.0,
                random_state=RANDOM_SEED,
            ),
        ),
        (
            "RandomForest",
            lambda: RandomForestRegressor(
                n_estimators=300,
                min_samples_leaf=2,
                max_features=0.8,
                n_jobs=4,
                random_state=RANDOM_SEED,
            ),
        ),
        (
            "ExtraTrees",
            lambda: ExtraTreesRegressor(
                n_estimators=300,
                min_samples_leaf=2,
                max_features=0.8,
                n_jobs=4,
                random_state=RANDOM_SEED,
            ),
        ),
        (
            "XGBoost",
            lambda: XGBRegressor(
                n_estimators=500,
                max_depth=5,
                learning_rate=0.04,
                subsample=0.85,
                colsample_bytree=0.85,
                objective="reg:squarederror",
                n_jobs=4,
                random_state=RANDOM_SEED,
            ),
        ),
        (
            "LightGBM",
            lambda: LGBMRegressor(
                n_estimators=500,
                num_leaves=31,
                learning_rate=0.04,
                subsample=0.85,
                colsample_bytree=0.85,
                reg_lambda=1.0,
                n_jobs=4,
                random_state=RANDOM_SEED,
                verbosity=-1,
            ),
        ),
    ]
    for name, factory in models:
        print(f"Running {name}...")
        results.append(
            run_model(
                name,
                factory,
                X_train,
                y_train_delta,
                X_test,
                y_test,
            )
        )

    report = markdown_report(results, len(train), len(test))
    RESULTS_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"Saved benchmark report to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
