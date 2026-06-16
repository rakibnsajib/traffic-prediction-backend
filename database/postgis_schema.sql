CREATE EXTENSION IF NOT EXISTS postgis;

ALTER TABLE intersections
ADD COLUMN IF NOT EXISTS geom GEOGRAPHY(POINT, 4326);

UPDATE intersections
SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
WHERE geom IS NULL;

CREATE INDEX IF NOT EXISTS idx_intersections_geom
    ON intersections
    USING GIST (geom);

ALTER TABLE road_segments
ADD COLUMN IF NOT EXISTS geom GEOMETRY(LINESTRING, 4326);

CREATE INDEX IF NOT EXISTS idx_road_segments_geom
    ON road_segments
    USING GIST (geom);

