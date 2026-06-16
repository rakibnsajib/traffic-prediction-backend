from __future__ import annotations

import json
import os
import base64
import hashlib
import hmac
import secrets
from datetime import date, datetime
from typing import Any


DEFAULT_BANGLADESH_LOCATIONS = [
    ("gulshan_1_dhaka", "Gulshan 1, Dhaka", 23.7806, 90.4193),
    ("motijheel_dhaka", "Motijheel, Dhaka", 23.7330, 90.4172),
    ("uttara_dhaka", "Uttara, Dhaka", 23.8759, 90.3795),
    ("dhanmondi_32_dhaka", "Dhanmondi 32, Dhaka", 23.7516, 90.3776),
    ("shahbagh_dhaka", "Shahbagh, Dhaka", 23.7383, 90.3956),
    ("chattogram_city_gate", "Chattogram City Gate", 22.3676, 91.7827),
    ("sylhet_zindabazar", "Sylhet Zindabazar", 24.8949, 91.8687),
    ("cumilla_kandirpar", "Cumilla Kandirpar", 23.4619, 91.1850),
    ("rajshahi_shaheb_bazar", "Rajshahi Shaheb Bazar", 24.3745, 88.6042),
]

DEFAULT_BANGLADESH_CORRIDORS = [
    ("gulshan_motijheel", "Gulshan 1 to Motijheel", "gulshan_1_dhaka", "motijheel_dhaka"),
    ("uttara_shahbagh", "Uttara to Shahbagh", "uttara_dhaka", "shahbagh_dhaka"),
    ("dhanmondi_gulshan", "Dhanmondi 32 to Gulshan 1", "dhanmondi_32_dhaka", "gulshan_1_dhaka"),
    ("cumilla_motijheel", "Cumilla Kandirpar to Motijheel", "cumilla_kandirpar", "motijheel_dhaka"),
    ("chattogram_cumilla", "Chattogram City Gate to Cumilla", "chattogram_city_gate", "cumilla_kandirpar"),
]

DEFAULT_USERS = [
    ("Admin", "User", "admin@tmaps.com", "Admin123@#", "admin"),
    ("Jarin Tabassum", "Anisa", "jarin@tmaps.com", "User123@#", "user"),
    ("Nadia", "Rahman", "nadia@tmaps.com", "User123@#", "user"),
    ("Tanvir", "Hasan", "tanvir@tmaps.com", "User123@#", "user"),
    ("Ayesha", "Karim", "ayesha@tmaps.com", "User123@#", "user"),
]

PASSWORD_ITERATIONS = 120_000


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt_bytes = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, PASSWORD_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_ITERATIONS,
        base64.b64encode(salt_bytes).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, digest = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt_bytes = base64.b64decode(salt.encode("ascii"))
        expected = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt_bytes,
            int(iterations),
        )
        return hmac.compare_digest(base64.b64encode(expected).decode("ascii"), digest)
    except (ValueError, TypeError):
        return False


def _json_load(value: Any) -> Any:
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _iso(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


class PostgresStore:
    def __init__(self) -> None:
        self.database_url = os.getenv("DATABASE_URL", "")
        if self.database_url:
            self._init_db()

    def _connect(self):
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not configured.")
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("Install psycopg[binary] to use PostgreSQL persistence.") from exc
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def _init_db(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS route_queries (
                        id BIGSERIAL PRIMARY KEY,
                        source_json JSONB NOT NULL,
                        destination_json JSONB NOT NULL,
                        departure_time TIMESTAMPTZ,
                        eta_minutes DOUBLE PRECISION,
                        distance_km DOUBLE PRECISION,
                        traffic_level TEXT,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS alerts (
                        id BIGSERIAL PRIMARY KEY,
                        severity TEXT NOT NULL,
                        title TEXT NOT NULL,
                        message TEXT NOT NULL,
                        context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        status TEXT NOT NULL DEFAULT 'active',
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bangladesh_locations (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        lat DOUBLE PRECISION NOT NULL,
                        lng DOUBLE PRECISION NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bangladesh_corridors (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        source_location_id TEXT NOT NULL REFERENCES bangladesh_locations(id),
                        destination_location_id TEXT NOT NULL REFERENCES bangladesh_locations(id)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id BIGSERIAL PRIMARY KEY,
                        first_name TEXT NOT NULL,
                        last_name TEXT NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
                        photo_url TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_route_queries_created_at
                    ON route_queries (created_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_alerts_status_created_at
                    ON alerts (status, created_at DESC)
                    """
                )
                cur.executemany(
                    """
                    INSERT INTO bangladesh_locations (id, name, lat, lng)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        lat = EXCLUDED.lat,
                        lng = EXCLUDED.lng
                    """,
                    DEFAULT_BANGLADESH_LOCATIONS,
                )
                cur.executemany(
                    """
                    INSERT INTO bangladesh_corridors (
                        id, name, source_location_id, destination_location_id
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        source_location_id = EXCLUDED.source_location_id,
                        destination_location_id = EXCLUDED.destination_location_id
                    """,
                    DEFAULT_BANGLADESH_CORRIDORS,
                )
                cur.executemany(
                    """
                    INSERT INTO users (first_name, last_name, email, password_hash, role)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (email) DO NOTHING
                    """,
                    [
                        (first, last, email, _hash_password(password), role)
                        for first, last, email, password, role in DEFAULT_USERS
                    ],
                )
            conn.commit()

    @staticmethod
    def _public_user(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "email": row["email"],
            "role": row["role"],
            "photo_url": row.get("photo_url"),
        }

    def authenticate_user(self, email: str, password: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, first_name, last_name, email, password_hash, role, photo_url
                FROM users
                WHERE lower(email) = lower(%s)
                """,
                (email.strip(),),
            ).fetchone()
        if not row or not _verify_password(password, row["password_hash"]):
            return None
        return self._public_user(row)

    def create_user(self, record: dict[str, str]) -> dict[str, Any]:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM users WHERE lower(email) = lower(%s)",
                (record["email"].strip(),),
            ).fetchone()
            if existing:
                raise ValueError("Email is already registered.")
            with conn.cursor() as cur:
                row = cur.execute(
                    """
                    INSERT INTO users (first_name, last_name, email, password_hash, role)
                    VALUES (%s, %s, %s, %s, 'user')
                    RETURNING id, first_name, last_name, email, role, photo_url
                    """,
                    (
                        record["first_name"].strip(),
                        record["last_name"].strip(),
                        record["email"].strip().lower(),
                        _hash_password(record["password"]),
                    ),
                ).fetchone()
            conn.commit()
        return self._public_user(row)

    def update_user_profile(self, record: dict[str, Any]) -> dict[str, Any]:
        user_id = int(record["id"])
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM users WHERE lower(email) = lower(%s) AND id <> %s",
                (record["email"].strip(), user_id),
            ).fetchone()
            if existing:
                raise ValueError("Email is already registered.")

            password = record.get("password") or ""
            if password:
                row = conn.execute(
                    """
                    UPDATE users
                    SET first_name = %s,
                        last_name = %s,
                        email = %s,
                        password_hash = %s,
                        photo_url = %s
                    WHERE id = %s
                    RETURNING id, first_name, last_name, email, role, photo_url
                    """,
                    (
                        record["first_name"].strip(),
                        record["last_name"].strip(),
                        record["email"].strip().lower(),
                        _hash_password(password),
                        record.get("photo_url"),
                        user_id,
                    ),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    UPDATE users
                    SET first_name = %s,
                        last_name = %s,
                        email = %s,
                        photo_url = %s
                    WHERE id = %s
                    RETURNING id, first_name, last_name, email, role, photo_url
                    """,
                    (
                        record["first_name"].strip(),
                        record["last_name"].strip(),
                        record["email"].strip().lower(),
                        record.get("photo_url"),
                        user_id,
                    ),
                ).fetchone()
            conn.commit()
        if not row:
            raise ValueError("User was not found.")
        return self._public_user(row)

    def insert_route_query(self, record: dict[str, Any]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO route_queries (
                        source_json,
                        destination_json,
                        departure_time,
                        eta_minutes,
                        distance_km,
                        traffic_level,
                        created_at
                    ) VALUES (%s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
                    """,
                    (
                        json.dumps(record["source"]),
                        json.dumps(record["destination"]),
                        record.get("departure_time"),
                        record.get("eta_minutes"),
                        record.get("distance_km"),
                        record.get("traffic_level"),
                        record.get("created_at"),
                    ),
                )
            conn.commit()

    def list_route_queries(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_json, destination_json, departure_time, eta_minutes,
                       distance_km, traffic_level, created_at
                FROM route_queries
                ORDER BY id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "source": _json_load(row["source_json"]),
                "destination": _json_load(row["destination_json"]),
                "departure_time": _iso(row["departure_time"]),
                "eta_minutes": row["eta_minutes"],
                "distance_km": row["distance_km"],
                "traffic_level": row["traffic_level"],
                "created_at": _iso(row["created_at"]),
            }
            for row in rows
        ]

    def insert_alert(self, record: dict[str, Any]) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                row = cur.execute(
                    """
                    INSERT INTO alerts (severity, title, message, context_json, status, created_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                    RETURNING id
                    """,
                    (
                        record["severity"],
                        record["title"],
                        record["message"],
                        json.dumps(record.get("context", {})),
                        record.get("status", "active"),
                        record["created_at"],
                    ),
                ).fetchone()
            conn.commit()
        return int(row["id"])

    def list_alerts(self, limit: int = 20, active_only: bool = False) -> list[dict[str, Any]]:
        params: list[Any] = []
        query = """
            SELECT id, severity, title, message, context_json, status, created_at
            FROM alerts
        """
        if active_only:
            query += " WHERE status = %s"
            params.append("active")
        query += " ORDER BY id DESC LIMIT %s"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "id": row["id"],
                "severity": row["severity"],
                "title": row["title"],
                "message": row["message"],
                "context": _json_load(row["context_json"]),
                "status": row["status"],
                "created_at": _iso(row["created_at"]),
            }
            for row in rows
        ]

    def list_bangladesh_locations(self) -> list[dict[str, Any]]:
        if not self.database_url:
            return [
                {"id": item[0], "name": item[1], "lat": item[2], "lng": item[3]}
                for item in DEFAULT_BANGLADESH_LOCATIONS
            ]
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, lat, lng
                FROM bangladesh_locations
                ORDER BY name
                """
            ).fetchall()
        return [
            {"id": row["id"], "name": row["name"], "lat": row["lat"], "lng": row["lng"]}
            for row in rows
        ]

    def list_bangladesh_corridors(self) -> list[dict[str, Any]]:
        if not self.database_url:
            locations = {
                item[0]: {"id": item[0], "name": item[1], "lat": item[2], "lng": item[3]}
                for item in DEFAULT_BANGLADESH_LOCATIONS
            }
            return [
                {
                    "id": item[0],
                    "corridor": item[1],
                    "from": locations[item[2]],
                    "to": locations[item[3]],
                }
                for item in DEFAULT_BANGLADESH_CORRIDORS
            ]
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    c.id,
                    c.name,
                    s.id AS source_id,
                    s.name AS source_name,
                    s.lat AS source_lat,
                    s.lng AS source_lng,
                    d.id AS destination_id,
                    d.name AS destination_name,
                    d.lat AS destination_lat,
                    d.lng AS destination_lng
                FROM bangladesh_corridors c
                JOIN bangladesh_locations s ON s.id = c.source_location_id
                JOIN bangladesh_locations d ON d.id = c.destination_location_id
                ORDER BY c.id
                """
            ).fetchall()
        return [
            {
                "id": row["id"],
                "corridor": row["name"],
                "from": {
                    "id": row["source_id"],
                    "name": row["source_name"],
                    "lat": row["source_lat"],
                    "lng": row["source_lng"],
                },
                "to": {
                    "id": row["destination_id"],
                    "name": row["destination_name"],
                    "lat": row["destination_lat"],
                    "lng": row["destination_lng"],
                },
            }
            for row in rows
        ]


local_store = PostgresStore()
