"""Application settings — Pydantic Settings + YAML/env hybrid.

Order of precedence (lowest → highest):

1. Module defaults below.
2. YAML file ``configs/{GPS_ENV}.yaml`` (default: ``configs/dev.yaml``).
3. Env vars prefixed with ``GPS_``.
4. ``.env`` file in the working directory.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ── Nested sub-schemas (loaded from YAML) ────────────────────────────────────


class StayPointConfig(BaseModel):
    time_threshold_minutes: int = 30
    distance_threshold_meters: int = 200


class ClusteringConfig(BaseModel):
    eps_meters: float = 100.0
    min_samples: int = 3


class ClassificationConfig(BaseModel):
    home_hour_start: int = 22
    home_hour_end: int = 6
    office_hour_start: int = 9
    office_hour_end: int = 18
    work_days: tuple = (0, 1, 2, 3, 4)
    min_confidence: float = 0.3
    min_duration_minutes: float = 30.0
    top_poi_n: int = 5
    geohash_precision: int = 6


class APIConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 1
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: List[str] = ["*"]


# ── Main Settings (env-overridable for production Cloud Run) ────────────────


class Settings(BaseSettings):
    """Top-level settings — flat GPS_* fields can be overridden via env vars."""

    # Environment + meta
    GPS_ENV: Literal["dev", "staging", "prod"] = "dev"
    GPS_APP_NAME: str = "gps-home-office-inference"
    GPS_APP_VERSION: str = "0.1.0"
    GPS_LOG_LEVEL: str = "INFO"

    # Paths (GeoLife structure):
    #   data/Geolife Trajectories 1.3/  ← raw .plt files
    #   data/processed/                ← general processed output
    #   data/processed_v1/              ← v1 heuristic model output
    GPS_DATA_DIR: Path = Path("./data")
    GPS_RAW_DATA_DIR: Path = Path("./data/Geolife Trajectories 1.3")
    GPS_PROCESSED_DATA_DIR: Path = Path("./data/processed")
    GPS_PROCESSED_V1_DIR: Path = Path("./data/processed_v1")
    GPS_MODEL_DIR: Path = Path("./models")

    # Model selection
    GPS_MODEL_VERSION: str = "v1"
    GPS_API_PORT: int = 8080
    GPS_PROMETHEUS_PORT: int = 9090

    # Nested YAML-only blocks (use gps.config.get_settings() to populate)
    stay_point: StayPointConfig = Field(default_factory=StayPointConfig)
    clustering: ClusteringConfig = Field(default_factory=ClusteringConfig)
    classification: ClassificationConfig = Field(default_factory=ClassificationConfig)
    api: APIConfig = Field(default_factory=APIConfig)

    model_config = SettingsConfigDict(
        env_prefix="GPS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# ── Loaders ──────────────────────────────────────────────────────────────────


# src/gps/config/settings.py → configs/ (3 levels up: gps → src → root)
CONFIG_DIR = Path(__file__).resolve().parents[3] / "configs"


def _yaml_path_for(env: str) -> Path | None:
    """Return configs/{env}.yaml if it exists, else configs/dev.yaml."""
    candidate = CONFIG_DIR / f"{env}.yaml"
    if candidate.exists():
        return candidate
    fallback = CONFIG_DIR / "dev.yaml"
    return fallback if fallback.exists() else None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build the active Settings, layering YAML over Pydantic defaults."""
    env = os.getenv("GPS_ENV", "dev").lower()
    yaml_path = _yaml_path_for(env)
    yaml_data: dict = {}
    if yaml_path:
        with open(yaml_path, "r", encoding="utf-8") as fp:
            yaml_data = yaml.safe_load(fp) or {}

    # Flat GPS_* env vars + .env are picked up automatically by Pydantic.
    # We only feed the nested blocks (stay_point/clustering/...) from YAML.
    return Settings(
        stay_point=yaml_data.get("stay_point", {}),
        clustering=yaml_data.get("clustering", {}),
        classification=yaml_data.get("classification", {}),
        api=yaml_data.get("api", {}),
    )
