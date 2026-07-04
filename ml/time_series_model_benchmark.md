# Time-Series Model Benchmark

## Setup

- Dataset: US Traffic Data with Weather and Calendar (PeMS)
- Forecast horizon: 15 minutes
- Split: chronological 80/20
- Training rows: 27791
- Test rows: 6948
- Features: current speed/flow, 5–60 minute lags, rolling statistics, time, and weather
- Ranking metric: lowest MAE

## Results

| Rank | Model | MAE (km/h) | RMSE (km/h) | R² |
|---:|---|---:|---:|---:|
| 1 | XGBoost | 1.0210 | 2.0494 | 0.7223 |
| 2 | HistGradientBoosting | 1.0361 | 2.0632 | 0.7186 |
| 3 | RandomForest | 1.0365 | 2.0464 | 0.7231 |
| 4 | LightGBM | 1.0387 | 2.0588 | 0.7198 |
| 5 | ExtraTrees | 1.0802 | 2.1080 | 0.7062 |

## Conclusion

**Best benchmark model: XGBoost**, with MAE
`1.0210 km/h`.

XGBoost is selected for the production model. The benchmark uses historical lag
and rolling features; the live production model uses only inputs available at
request time, so its production metrics are reported separately in
`model_metrics.json`.
