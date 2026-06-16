CREATE TABLE IF NOT EXISTS route_queries (
    id BIGSERIAL PRIMARY KEY,
    source_json JSONB NOT NULL,
    destination_json JSONB NOT NULL,
    departure_time TIMESTAMPTZ,
    eta_minutes DOUBLE PRECISION,
    distance_km DOUBLE PRECISION,
    traffic_level TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS bangladesh_locations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    lng DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS bangladesh_corridors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_location_id TEXT NOT NULL REFERENCES bangladesh_locations(id),
    destination_location_id TEXT NOT NULL REFERENCES bangladesh_locations(id)
);

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
    photo_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_route_queries_created_at
    ON route_queries (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_status_created_at
    ON alerts (status, created_at DESC);
