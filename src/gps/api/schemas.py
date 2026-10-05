"""Pydantic schemas for API request/response validation.

The classify endpoint takes **stay-points**, in the same shape the pipeline writes to
``data/processed/staypoints/user_{id}.parquet`` (``gps.features.stay_point.stay_points_to_frame``).
Raw GPS points are not accepted: stay-point detection runs in the pipeline, where its
thresholds are validated (notebooks 04-10).

| Field              | Pipeline column    | Unit        | Notes |
|--------------------|--------------------|-------------|-------|
| ``lat`` / ``lon``  | ``lat`` / ``lon``  | decimal deg | WGS84, stay centroid |
| ``arrival_time``   | ``arrival``        | naive GMT   | tz-aware input is converted to GMT |
| ``departure_time`` | ``departure``      | naive GMT   | must be after ``arrival_time`` |
| ``observed_minutes`` | ``observed_minutes`` | minutes | optional; time actually covered by GPS points |
| ``altitude_m``     | ``altitude_m``     | metres      | optional |
"""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _to_naive_gmt(value: datetime) -> datetime:
    """GeoLife and the pipeline use naive GMT; convert tz-aware input to that."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


class StayPointInput(BaseModel):
    """One stay-point: where the user stayed, from when to when."""

    lat: float = Field(..., ge=-90, le=90, description="Latitude of the stay centroid (decimal degrees, WGS84)")
    lon: float = Field(..., ge=-180, le=180, description="Longitude of the stay centroid (decimal degrees, WGS84)")
    arrival_time: datetime = Field(
        ..., description="Arrival (ISO-8601). Naive values are GMT, as in GeoLife; tz-aware values are converted to GMT.")
    departure_time: datetime = Field(..., description="Departure (ISO-8601), after arrival_time. Same time convention.")
    observed_minutes: float | None = Field(
        default=None, ge=0,
        description="Minutes of the stay actually covered by GPS points (gaps > 20 min excluded); "
                    "at most departure - arrival.")
    altitude_m: float | None = Field(default=None, description="Mean altitude in metres (optional).")

    @field_validator("arrival_time", "departure_time")
    @classmethod
    def as_naive_gmt(cls, v: datetime) -> datetime:
        return _to_naive_gmt(v)

    @model_validator(mode="after")
    def check_times(self) -> "StayPointInput":
        if self.departure_time <= self.arrival_time:
            raise ValueError("departure_time must be after arrival_time")
        duration = (self.departure_time - self.arrival_time).total_seconds() / 60
        if self.observed_minutes is not None and self.observed_minutes > duration + 1e-6:
            raise ValueError("observed_minutes cannot exceed departure_time - arrival_time")
        return self


class ClassificationRequest(BaseModel):
    """Request schema for the classification endpoint (the user id is in the URL)."""
    stay_points: list[StayPointInput] = Field(
        ...,
        min_length=1,
        description="The user's stay-points, e.g. rows of data/processed/staypoints/user_{id}.parquet",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "stay_points": [
                    {
                        "lat": 39.9847,
                        "lon": 116.3184,
                        "arrival_time":   "2008-10-23T14:30:00",
                        "departure_time": "2008-10-23T22:45:00",
                        "observed_minutes": 480.0,
                        "altitude_m": 50.0,
                    },
                    {
                        "lat": 40.0043,
                        "lon": 116.3263,
                        "arrival_time":   "2008-10-24T01:00:00",
                        "departure_time": "2008-10-24T10:30:00",
                    },
                ],
            }
        }
    }


class LocationOutput(BaseModel):
    """Output schema for a classified location.

    ## Confidence score
    The ``confidence`` field is a **heuristic** value in [0, 1] — NOT a
    supervised-learning probability. It is computed as:

        confidence = winner_dwell_time / total_type_dwell_time

    where ``winner`` is the most-visited (or longest-dwell) stay-point
    cluster for that location type and ``type`` is one of
    ``"home" / "office" / "poi"``. The intuition: if a single location
    captures most of the user's time inside the expected time-window
    (e.g. nights for home, work-hours for office) we are confident
    that this is *the* home/office.

    Because GeoLife has no ground-truth home/office labels, we cannot
    train a calibrated probability; this is a deterministic,
    reproducible heuristic and should be treated as a relative score
    for ranking candidates rather than an absolute probability.
    """

    lat: float = Field(..., description="Latitude")
    lon: float = Field(..., description="Longitude")
    location_type: Literal["home", "office", "poi", "unknown"] = Field(
        ...,
        description="Type of location",
    )
    confidence: float = Field(
        ...,
        ge=0,
        le=1,
        description=(
            "Heuristic score [0..1] — share of the user's time spent at "
            "this location within the expected time-window (see LocationOutput "
            "docstring). Not a learned probability."
        ),
    )
    visit_count: int = Field(
        default=1,
        ge=1,
        description="Number of visits to this location"
    )
    duration_minutes: float = Field(
        default=0,
        ge=0,
        description="Total dwell time across all visits (minutes)"
    )
    altitude_m: float | None = Field(
        default=None,
        description="Mean altitude (metres) over the visits to this location; "
                    "null means altitude was not provided in the input.",
    )
    first_seen: datetime | None = Field(
        default=None,
        description="First visit timestamp (naive GMT)"
    )
    last_seen: datetime | None = Field(
        default=None,
        description="Most recent visit timestamp (naive GMT)"
    )
    geohash: str | None = Field(
        default=None,
        description="Geohash encoding for privacy"
    )


class ClassificationResponse(BaseModel):
    """Response schema for classification endpoint."""
    user_id: str = Field(..., description="User identifier")
    locations: list[LocationOutput] = Field(
        ...,
        description="All detected locations"
    )
    home: LocationOutput | None = Field(
        default=None,
        description="Inferred home location"
    )
    office: LocationOutput | None = Field(
        default=None,
        description="Inferred office location"
    )
    pois: list[LocationOutput] = Field(
        default_factory=list,
        description="Points of Interest"
    )
    model_version: str = Field(..., description="Model version used")
    processed_at: datetime = Field(
        default_factory=datetime.now,
        description="Processing timestamp"
    )


class HealthResponse(BaseModel):
    """Response schema for health endpoints."""
    status: Literal["healthy", "ready"] = Field(..., description="Health status")
    version: str = Field(..., description="API version")
    model_version: str = Field(..., description="Loaded model version")


class ErrorResponse(BaseModel):
    """Response schema for errors."""
    detail: str = Field(..., description="Error message")
    error_code: str | None = Field(default=None, description="Error code")
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Error timestamp"
    )


class BatchClassificationRequest(BaseModel):
    """Request schema for batch classification."""
    users: list[ClassificationRequest] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of user classification requests"
    )


class BatchClassificationResponse(BaseModel):
    """Response schema for batch classification."""
    results: list[ClassificationResponse] = Field(
        ...,
        description="Classification results"
    )
    total_users: int = Field(..., description="Total users processed")
    failed_count: int = Field(default=0, description="Number of failed requests")
