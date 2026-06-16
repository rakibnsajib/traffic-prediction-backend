import os
from dataclasses import dataclass


@dataclass
class DatabaseSettings:
    postgres_url: str = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/traffic_prediction"
    )
    neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user: str = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "password")


db_settings = DatabaseSettings()
