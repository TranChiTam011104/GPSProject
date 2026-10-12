"""Base classes for home/office classifiers.

Both v1 (heuristic-on-stay-points) and v2 (heuristic-on-clusters) share the
same shape so :mod:`gps.api.dependencies` can pick the right one by name.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from geohash2 import encode as geohash_encode

# ── Output value objects ─────────────────────────────────────────────────────


@dataclass
class Location:
    """A single inferred location (home / office / POI / unknown).

    ## Confidence definition (heuristic, NOT supervised probability)

    ``confidence = winner_window_minutes / total_type_window_minutes``

    - ``winner`` — the stay-point (v1) that spent the most minutes inside the
      daily window of this location type. POIs use plain dwell time.
    - ``type``   — one of ``"home" / "office" / "poi"``.
    - Clamped to ``[0, 1]``.

    Why this works: GeoLife has no ground-truth home/office labels, so we
    cannot train a calibrated classifier. Instead, we exploit the natural
    time-windowing heuristic — a location that dominates *the* expected
    time-window (e.g. night hours for home, weekday 09:00–18:00 for office)
    is almost certainly the user's home/office. The score is deterministic
    and reproducible, useful as a relative ranking signal, not as an
    absolute probability.
    """

    lat: float
    lon: float
    location_type: str  # "home" | "office" | "poi" | "unknown"
    confidence: float   # 0..1
    visit_count: int = 1
    duration_minutes: float = 0.0
    altitude_m: float = 0.0
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    geohash: str | None = None

    def with_geohash(self, precision: int = 6) -> Location:
        if self.geohash is None:
            self.geohash = geohash_encode(self.lat, self.lon, precision=precision)
        return self

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PlaceStatus:
    """Whether a home / office answer was given, and the evidence behind it.

    ``status`` is ``"found"`` or ``"unknown"``. When unknown, ``reason`` is one of
    ``"no_candidate"`` (no stay-point has any minute in the window),
    ``"too_few_window_minutes"`` or ``"one_off_place"`` (see
    notebooks/13_minimum_evidence.ipynb: below these, a v1 answer repeats on another
    half of the user's data no better than a random candidate).

    The evidence is that of the best candidate and is kept when unknown, so callers
    can judge it themselves: ``window_minutes`` = its minutes inside the window,
    ``support`` = candidates within ``support_radius_m`` of it, itself included (how
    many times the user was at that place inside the window).
    """

    status: str = "unknown"
    reason: str | None = "no_candidate"
    window_minutes: float | None = None
    support: int | None = None


@dataclass
class ClassificationResult:
    """Result of classifying one user.

    ``home`` / ``office`` are ``None`` exactly when the matching status is unknown.
    """

    user_id: str
    locations: list[Location] = field(default_factory=list)
    home: Location | None = None
    office: Location | None = None
    home_status: PlaceStatus = field(default_factory=PlaceStatus)
    office_status: PlaceStatus = field(default_factory=PlaceStatus)
    pois: list[Location] = field(default_factory=list)
    model_version: str = "unknown"
    processed_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "locations": [loc.to_dict() for loc in self.locations],
            "home": self.home.to_dict() if self.home else None,
            "office": self.office.to_dict() if self.office else None,
            "home_status": asdict(self.home_status),
            "office_status": asdict(self.office_status),
            "pois": [loc.to_dict() for loc in self.pois],
            "model_version": self.model_version,
            "processed_at": self.processed_at.isoformat(),
        }


# ── Input value object ───────────────────────────────────────────────────────


@dataclass
class StayPointInput:
    """Normalised stay-point consumed by classifiers.

    Same fields as the API's :class:`gps.api.schemas.StayPointInput`, but lives here
    so the model layer does not depend on FastAPI. Times are naive GMT.
    """

    lat: float
    lon: float
    arrival_time: datetime
    departure_time: datetime
    observed_minutes: float | None = None
    altitude_m: float | None = None

    @property
    def duration_minutes(self) -> float:
        return (self.departure_time - self.arrival_time).total_seconds() / 60.0

    @classmethod
    def from_dict(cls, raw) -> StayPointInput:
        """Build from a dict or an object with matching attributes.

        Reads both the API names (``arrival_time`` / ``departure_time``) and the
        pipeline's column names (``arrival`` / ``departure``), so rows of
        ``data/processed/staypoints/user_{id}.parquet`` can be passed directly.
        Raises ``ValueError`` when a time is missing or departure is not after arrival.
        """
        arrival = _coerce_dt(_get_field(raw, "arrival_time", "arrival"))
        departure = _coerce_dt(_get_field(raw, "departure_time", "departure"))
        if departure <= arrival:
            raise ValueError("departure_time must be after arrival_time")
        return cls(
            lat=float(_get_field(raw, "lat")),
            lon=float(_get_field(raw, "lon")),
            arrival_time=arrival,
            departure_time=departure,
            observed_minutes=_optional_float(_get_field(raw, "observed_minutes", required=False)),
            altitude_m=_optional_float(_get_field(raw, "altitude_m", required=False)),
        )


def _coerce_dt(value) -> datetime:
    """datetime / pandas Timestamp / ISO string -> naive GMT datetime."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime):
        raise TypeError(f"Cannot coerce {value!r} to datetime")
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _optional_float(value) -> float | None:
    """None and NaN (missing in the pipeline's parquet) both mean "not given"."""
    if value is None:
        return None
    value = float(value)
    return None if math.isnan(value) else value


def _get_field(obj, *keys, required=True, default=None):
    """Try each key in order; return the first match, or raise (or return default)."""
    for key in keys:
        if hasattr(obj, key):          # attribute access (Pydantic model / dataclass)
            val = getattr(obj, key)
            if val is not None:
                return val
        if isinstance(obj, dict):     # dict access
            if key in obj:
                val = obj[key]
                if val is not None:
                    return val
    if required:
        raise ValueError(f"None of {keys} found in {obj!r}")
    return default


def coerce_stay_points(raw: Iterable) -> list[StayPointInput]:
    """Normalise API models, pipeline rows (dicts) and ``StayPoint`` objects from
    :mod:`gps.features.stay_point` to :class:`StayPointInput`."""
    out: list[StayPointInput] = []
    for r in raw:
        if isinstance(r, StayPointInput):
            out.append(r)
        elif hasattr(r, "model_dump"):                    # Pydantic (API request)
            out.append(StayPointInput.from_dict(r.model_dump()))
        elif hasattr(r, "__dataclass_fields__"):          # gps.features.stay_point.StayPoint
            out.append(StayPointInput.from_dict(asdict(r)))
        elif isinstance(r, dict):
            out.append(StayPointInput.from_dict(r))
        else:
            raise TypeError(f"Cannot coerce stay-point entry of type {type(r)}")
    return out


# ── Abstract classifier ─────────────────────────────────────────────────────


class BaseClassifier(ABC):
    """All classifiers must implement :meth:`predict` and report a version."""

    model_version: str = "base"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @abstractmethod
    def predict(self, stay_points: Iterable[dict]) -> ClassificationResult:
        """Run inference and return a :class:`ClassificationResult`."""

    def get_model_version(self) -> str:
        return self.model_version
