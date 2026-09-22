"""Pydantic schemas for API request/response validation.

These schemas mirror the GeoLife ``.plt`` row schema so callers can submit a
trajectory directly, not just pre-computed stay-points:

| Field          | Source in GeoLife .plt | Unit          | Notes |
|----------------|------------------------|---------------|-------|
| ``lat``        | col 0                  | decimal deg   | WGS84 |
| ``lng``        | col 1                  | decimal deg   | WGS84 |
| ``altitude_m`` | col 3 (feet) × 0.3048  | metres        | -777 sentinel already replaced upstream |
| ``timestamp``  | col 5+6 (``date_str``+``time_str``) | naive GMT | ISO-8601 when posted |
| ``accuracy``   | (optional)             | metres        | horizontal GPS accuracy if known |
| ``user_id``    | directory name         | string        | optional per-row override |

The classifier only consumes ``arrival_time``/``departure_time`` (i.e. the
already-aggregated stay-point), so ``lat``/``lng`` are kept for reference
and to enable future trajectory-level scoring.
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
from datetime import datetime


class StayPointInput(BaseModel):
    """Input schema for a single stay-point (pre-aggregated) **or** a single
    raw GPS observation.

    Required for *stay-points*:

    - ``arrival_time``  — when the user arrived at this location
    - ``departure_time`` — when they left (``arrival_time < departure_time``)

    Required for *raw GPS observations* (alternative use):

    - ``timestamp`` — naive GMT, parsed from GeoLife ``.plt`` date_str+time_str

    Either ``arrival_time`` **or** ``timestamp`` must be supplied; if both are
    present, ``timestamp`` is ignored by the classifier (the stay-point
    variant wins).
    """

    # ── Location ────────────────────────────────────────────────────────────
    lat: float = Field(..., ge=-90, le=90, description="Latitude (decimal degrees, WGS84)")
    lng: float = Field(..., ge=-180, le=180, description="Longitude (decimal degrees, WGS84)")

    # ── Stay-point semantics ────────────────────────────────────────────────
    arrival_time: Optional[datetime] = Field(
        default=None,
        description="When the user arrived at this location (ISO-8601, naive or tz-aware). "
                    "GeoLife timestamps are naive GMT; cloud devices (OwnTracks, Google "
                    "Takeout) post tz-aware. Required when posting an aggregated stay-point.",
    )
    departure_time: Optional[datetime] = Field(
        default=None,
        description="When the user left (ISO-8601, naive or tz-aware). Must be > arrival_time.",
    )
    duration_minutes: Optional[float] = Field(
        default=None,
        ge=0,
        description="Pre-computed dwell time in minutes (auto-calculated when arrival+departure set)",
    )

    # ── Raw GPS observation fields (optional) ───────────────────────────────
    timestamp: Optional[datetime] = Field(
        default=None,
        description="Raw timestamp (naive GMT) — only used when posting a single GPS "
                    "observation. Equivalent to arrival_time when both are absent.",
    )
    altitude_m: Optional[float] = Field(
        default=None,
        description="Altitude in metres (GeoLife raw is in feet: × 0.3048 upstream).",
    )
    accuracy: Optional[float] = Field(
        default=None,
        ge=0,
        description="Horizontal GPS accuracy in metres (optional).",
    )
    user_id: Optional[str] = Field(
        default=None,
        description="Per-row override of the user_id from the URL path (optional).",
    )

    # ── Validators ──────────────────────────────────────────────────────────

    @field_validator("departure_time")
    @classmethod
    def departure_after_arrival(cls, v, info):
        if v is None:
            return v
        arr = info.data.get("arrival_time")
        if arr is not None and v <= arr:
            raise ValueError("departure_time must be after arrival_time")
        return v

    @field_validator("duration_minutes")
    @classmethod
    def calculate_duration(cls, v, info):
        if v is not None:
            return v
        arr = info.data.get("arrival_time")
        dep = info.data.get("departure_time")
        if arr is not None and dep is not None:
            return (dep - arr).total_seconds() / 60.0
        return None

    @field_validator("arrival_time")
    @classmethod
    def fill_arrival_from_timestamp(cls, v, info):
        """If only ``timestamp`` is supplied, treat it as ``arrival_time``."""
        if v is None:
            ts = info.data.get("timestamp")
            if ts is not None:
                # ``timestamp`` is the only time signal — alias it.
                return ts
        return v


class ClassificationRequest(BaseModel):
    """Request schema for classification endpoint."""
    user_id: Optional[str] = Field(
        default=None,
        description="Optional global user_id for all stay-points in this request. "
                    "Per-row ``user_id`` stays take precedence.",
    )
    stay_points: List[StayPointInput] = Field(
        ...,
        min_length=1,
        description="List of stay-points from GPS trajectory",
    )
    include_geohash: bool = Field(
        default=True,
        description="Include geohash encoding in response",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "user_id": "010",
                "stay_points": [
                    {
                        "lat": 39.9847,
                        "lng": 116.3184,
                        "arrival_time":   "2008-10-23T22:30:00",
                        "departure_time": "2008-10-24T06:45:00",
                        "altitude_m": 50.0,
                    },
                    {
                        "lat": 39.9847,
                        "lng": 116.3185,
                        "arrival_time":   "2008-10-24T09:00:00",
                        "departure_time": "2008-10-24T18:30:00",
                        "altitude_m": 45.0,
                    },
                ],
                "include_geohash": True,
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
    lng: float = Field(..., description="Longitude")
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
    altitude_m: Optional[float] = Field(
        default=None,
        description="Mean altitude (metres) over the visits to this location; "
                    "null means altitude was not provided in the input.",
    )
    first_seen: Optional[datetime] = Field(
        default=None,
        description="First visit timestamp (naive GMT)"
    )
    last_seen: Optional[datetime] = Field(
        default=None,
        description="Most recent visit timestamp (naive GMT)"
    )
    geohash: Optional[str] = Field(
        default=None,
        description="Geohash encoding for privacy"
    )


class ClassificationResponse(BaseModel):
    """Response schema for classification endpoint."""
    user_id: str = Field(..., description="User identifier")
    locations: List[LocationOutput] = Field(
        ...,
        description="All detected locations"
    )
    home: Optional[LocationOutput] = Field(
        default=None,
        description="Inferred home location"
    )
    office: Optional[LocationOutput] = Field(
        default=None,
        description="Inferred office location"
    )
    pois: List[LocationOutput] = Field(
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
    error_code: Optional[str] = Field(default=None, description="Error code")
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Error timestamp"
    )


class BatchClassificationRequest(BaseModel):
    """Request schema for batch classification."""
    users: List[ClassificationRequest] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of user classification requests"
    )


class BatchClassificationResponse(BaseModel):
    """Response schema for batch classification."""
    results: List[ClassificationResponse] = Field(
        ...,
        description="Classification results"
    )
    total_users: int = Field(..., description="Total users processed")
    failed_count: int = Field(default=0, description="Number of failed requests")
