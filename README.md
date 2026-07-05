# Traffic Prediction Backend

FastAPI backend for route generation, traffic prediction, alerts, and dashboard data.

## Tech Stack

- FastAPI
- Uvicorn
- PostgreSQL
- XGBoost model artifact in `ml/`

## Environment

Create `backend/.env` from `.env.example`:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/traffic_prediction
GOOGLE_MAPS_API_KEY=your_google_maps_api_key
TOMTOM_API_KEY=your_tomtom_api_key
OPEN_METEO_CACHE_SECONDS=300
```

`DATABASE_URL` is required for PostgreSQL persistence. `GOOGLE_MAPS_API_KEY` is required for Google routing. Address search uses local Bangladesh suggestions, Photon, and Nominatim. `TOMTOM_API_KEY` supplies the current road speed used as the model's `previous_speed`. Open-Meteo supplies current weather without an API key. The live integrations fall back safely when unavailable.

TomTom Traffic Flow coverage varies by country and road. Unsupported points are cached briefly and use the model's existing fallback speed.

## Real Dataset and Training

The production XGBoost model is trained on the Kaggle **US Traffic Data with Weather and Calendar** dataset, containing 34,823 real five-minute PeMS traffic and weather observations. It forecasts speed 15 minutes ahead using current speed, time, temperature, humidity, precipitation, wind, and weather-condition flags.

```bash
python ml/train_model.py
```

The raw dataset is stored at `ml/real_data/traffic_weather_full2020.csv`. The training split is chronological to avoid leaking future observations into evaluation.

### Time-Series Model Benchmark

The isolated benchmark does not replace the production model:

```bash
pip install -r ml/benchmark_requirements.txt
python ml/benchmark_time_series_models.py
```

It compares persistence, HistGradientBoosting, Random Forest, Extra Trees, XGBoost, and LightGBM using the same chronological split and writes the report to `ml/time_series_model_benchmark.md`.

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Database

Create the database, then seed it:

```bash
createdb traffic_prediction
psql "$DATABASE_URL" -f database/postgresql_seed.sql
```

On Windows PowerShell:

```powershell
$env:PGPASSWORD="your_postgres_password"
psql -h localhost -U postgres -d traffic_prediction -f database/postgresql_seed.sql
```

## Run Locally

```bash
uvicorn app.main:app --reload --port 8000
```

Health check:

```text
http://localhost:8000/health
```

## Test

```bash
pytest -q
```

## Railway Deployment

1. Push only the `backend/` folder to its own GitHub repository.
2. Create a Railway project from that repository.
3. Add a Railway PostgreSQL service.
4. Set backend service variables:

```env
DATABASE_URL=<Railway PostgreSQL connection URL>
GOOGLE_MAPS_API_KEY=<your_google_maps_api_key>
```

5. Railway uses `railway.json`:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

6. Seed Railway PostgreSQL:

```bash
psql "<RAILWAY_DATABASE_URL>" -f database/postgresql_seed.sql
```

## Main Endpoints

- `GET /health`
- `POST /api/route`
- `POST /api/predict-traffic`
- `GET /api/model-metrics`
- `GET /api/sample-traffic-data`
- `GET /api/recent-route-queries`
- `GET /api/alerts`
- `GET /api/alerts/active`
- `GET /api/dashboard-reference-data`
