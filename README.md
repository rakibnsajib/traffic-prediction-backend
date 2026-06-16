# Traffic Prediction Backend

FastAPI backend for route generation, traffic prediction, alerts, and dashboard data.

## Tech Stack

- FastAPI
- Uvicorn
- PostgreSQL
- scikit-learn model artifacts in `ml/`

## Environment

Create `backend/.env` from `.env.example`:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/traffic_prediction
GOOGLE_MAPS_API_KEY=your_google_maps_api_key
```

`DATABASE_URL` is required for PostgreSQL persistence. `GOOGLE_MAPS_API_KEY` is required for Google routing/geocoding.

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
