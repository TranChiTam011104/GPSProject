"""
Pydantic schemas for API request/response validation.
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
from datetime import datetime


class StayPointInput(BaseModel):
    """Input schema for a single stay-point."""
    lat: float = Field(..., ge=-90, le=90, description="Latitude")
    lng: float = Field(..., ge=-180, le=180, description="Longitude")
    arrival_time: datetime = Field(..., description="Arrival timestamp")
    departure_time: datetime = Field(..., description="Departure timestamp")
    duration_minutes: Optional[float] = Field(
        default=None,
        ge=0,
        description="Duration in minutes (auto-calculated if not provided)"
    )

    @field_validator("departure_time")
    @classmethod
    def departure_after_arrival(cls, v, info):
        if "arrival_time" in info.data and v <= info.data["arrival_time"]:
            raise ValueError("departure_time must be after arrival_time")
        return v

    @field_validator("duration_minutes")
    @classmethod
    def calculate_duration(cls, v, info):
        if v is None and "arrival_time" in info.data and "departure_time" in info.data:
            delta = info.data["departure_time"] - info.data["arrival_time"]
            return delta.total_seconds() / 60
        return v


class ClassificationRequest(BaseModel):
    """Request schema for classification endpoint."""
    stay_points: List[StayPointInput] = Field(
        ...,
        min_length=1,
        description="List of stay-points from GPS trajectory"
    )
    include_geohash: bool = Field(
        default=True,
        description="Include geohash encoding in response"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "stay_points": [
                    {
                        "lat": 39.9847,
                        "lng": 116.3184,
                        "arrival_time": "2008-10-23T22:30:00",
                        "departure_time": "2008-10-24T06:45:00"
                    },
                    {
                        "lat": 39.9847,
                        "lng": 116.3185,
                        "arrival_time": "2008-10-24T09:00:00",
                        "departure_time": "2008-10-24T18:30:00"
                    }
                ],
                "include_geohash": True
            }
        }
    }


class LocationOutput(BaseModel):
    """Output schema for a classified location."""
    lat: float = Field(..., description="Latitude")
    lng: float = Field(..., description="Longitude")
    location_type: Literal["home", "office", "poi", "unknown"] = Field(
        ...,
        description="Type of location"
    )
    confidence: float = Field(
        ...,
        ge=0,
        le=1,
        description="Confidence score (0-1)"
    )
    visit_count: int = Field(
        default=1,
        ge=1,
        description="Number of visits to this location"
    )
    duration_minutes: float = Field(
        default=0,
        ge=0,
        description="Total duration at this location"
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
