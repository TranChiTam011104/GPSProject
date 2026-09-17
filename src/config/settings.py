"""
Application settings and configuration.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List, Optional
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    app_name: str = "gps-home-office-inference"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 1

    # AWS
    aws_region: str = "us-east-1"
    aws_profile: Optional[str] = None
    s3_bucket: str = ""
    sqs_queue_url: str = ""

    # MLflow
    mlflow_tracking_uri: str = "http://localhost:5000"
    mlflow_experiment_name: str = "gps-inference"

    # Model
    model_version: str = "v1"
    model_path: str = "./models/v1"
    model_registry: str = ""

    # Stay-point detection
    stay_point_time_threshold_minutes: int = 30
    stay_point_distance_threshold_meters: int = 200

    # DBSCAN
    dbscan_eps_meters: float = 100.0
    dbscan_min_samples: int = 3

    # Privacy
    geohash_precision: int = 6
    k_anonymity_k: int = 5

    # Monitoring
    prometheus_port: int = 9090
    enable_drift_detection: bool = True

    # CORS
    cors_origins: List[str] = ["*"]

    # Paths
    data_dir: str = "./data"
    raw_data_dir: str = "./data/raw"
    processed_data_dir: str = "./data/processed"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
