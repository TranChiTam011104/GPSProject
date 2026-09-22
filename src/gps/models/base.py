"""Base classes for home/office classifiers.

Both v1 (heuristic-on-stay-points) and v2 (heuristic-on-clusters) share the
same shape so :mod:`gps.api.dependencies` can pick the right one by name.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Iterable, List, Optional

from geohash2 import encode as geohash_encode


# ── Output value objects ─────────────────────────────────────────────────────


@dataclass
class Location:
    """A single inferred location (home / office / POI / unknown).

    ## Confidence definition (heuristic, NOT supervised probability)

    ``confidence = winner_dwell_time / total_type_dwell_time``

    - ``winner`` — the single (lat, lng) bucket that captured the most dwell
      time (and visits) for this location type.
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
    lng: float
    location_type: str  # "home" | "office" | "poi" | "unknown"
    confidence: float   # 0..1
    visit_count: int = 1
    duration_minutes: float = 0.0
    altitude_m: float = 0.0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    geohash: Optional[str] = None

    def with_geohash(self, precision: int = 6) -> "Location":
        if self.geohash is None:
            self.geohash = geohash_encode(self.lat, self.lng, precision=precision)
        return self

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ClassificationResult:
    """Result of classifying one user."""

    user_id: str
    locations: List[Location] = field(default_factory=list)
    home: Optional[Location] = None
    office: Optional[Location] = None
    pois: List[Location] = field(default_factory=list)
    model_version: str = "unknown"
    processed_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "locations": [loc.to_dict() for loc in self.locations],
            "home": self.home.to_dict() if self.home else None,
            "office": self.office.to_dict() if self.office else None,
            "pois": [loc.to_dict() for loc in self.pois],
            "model_version": self.model_version,
            "processed_at": self.processed_at.isoformat(),
        }


# ── Input value object ───────────────────────────────────────────────────────


@dataclass
class StayPointInput:
    """Normalised stay-point consumed by classifiers.

    Mirrors the Pydantic :class:`gps.api.schemas.StayPointInput` but lives here
    so the model layer does not depend on FastAPI.

    Fields are optional except ``lat``/``lng``/``arrival_time``/``departure_time``
    so the same shape can carry either:

    - an aggregated stay-point (caller already computed the dwell window), or
    - a single raw GPS observation (only ``timestamp`` is set; we alias it to
      ``arrival_time`` in :meth:`from_dict`).
    """

    lat: float
    lng: float
    arrival_time: datetime
    departure_time: datetime
    altitude_m: float = 0.0
    accuracy: float = 0.0
    user_id: Optional[str] = None

    @property
    def duration_minutes(self) -> float:
        return (self.departure_time - self.arrival_time).total_seconds() / 60.0

    @classmethod
    def from_dict(cls, raw: dict) -> "StayPointInput":
        """Best-effort coercion from the FastAPI request shape.

        Accepts dicts, Pydantic v1/v2 models, and arbitrary objects with
        matching attribute names. Aliases:

        - ``lat`` / ``latitude``
        - ``lng`` / ``lon`` / ``longitude``
        - ``arrival_time`` / ``start_time``
        - ``departure_time`` / ``end_time``
        - ``altitude_m`` / ``altitude`` (raw feet; call :func:`clean_altitude` upstream)
        - ``accuracy`` (optional)
        - ``user_id`` (optional)

        If only ``timestamp`` is supplied (raw GPS row), it is aliased to
        ``arrival_time`` and ``departure_time`` is set to the same instant
        (zero-duration stay-point — downstream filters with
        ``min_duration_minutes``).
        """
        lat = _get_field(raw, "lat", "latitude")
        lng = _get_field(raw, "lng", "lon", "longitude")
        arr = _get_field(raw, "arrival_time", "start_time", required=False)
        dep = _get_field(raw, "departure_time", "end_time", required=False)
        ts = _get_field(raw, "timestamp", required=False)

        # Raw observation fallback: alias `timestamp` to both arrival and departure.
        if arr is None and ts is not None:
            arr = ts
            dep = ts
        if arr is None or dep is None:
            raise ValueError(
                "StayPointInput needs either arrival_time/departure_time or timestamp"
            )

        alt = _get_field(raw, "altitude_m", "altitude", required=False, default=0.0)
        accuracy = _get_field(raw, "accuracy", required=False, default=0.0)
        user_id = _get_field(raw, "user_id", required=False, default=None)

        return cls(
            lat=float(lat),
            lng=float(lng),
            arrival_time=_coerce_dt(arr),
            departure_time=_coerce_dt(dep),
            altitude_m=float(alt) if alt is not None else 0.0,
            accuracy=float(accuracy) if accuracy is not None else 0.0,
            user_id=user_id,
        )


def _coerce_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"Cannot coerce {value!r} to datetime")


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


def coerce_stay_points(raw: Iterable) -> List[StayPointInput]:
    """Accept dicts, ``StayPointInput`` objects, or Pydantic v2 models.

    FastAPI routes pass Pydantic models, notebooks pass dicts, unit tests pass
    both. The coercion normalises to ``StayPointInput`` so the rest of the
    classifier only needs to handle that one type.
    """
    out: List[StayPointInput] = []
    for r in raw:
        if isinstance(r, StayPointInput):
            out.append(r)
            continue
        # Pydantic v2 BaseModel — pull the fields we need.
        if hasattr(r, "model_dump"):
            r = r.model_dump()
        # Pydantic v1 (legacy).
        elif hasattr(r, "dict") and callable(r.dict):
            r = r.dict()
        if isinstance(r, dict):
            out.append(StayPointInput.from_dict(r))
        else:
            raise TypeError(f"Cannot coerce stay-point entry of type {type(r)}")
    return out


# ── Abstract classifier ─────────────────────────────────────────────────────


class BaseClassifier(ABC):
    """All classifiers must implement :meth:`predict` and report a version."""

    model_version: str = "base"

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    @abstractmethod
    def predict(self, stay_points: Iterable[dict]) -> ClassificationResult:
        """Run inference and return a :class:`ClassificationResult`."""

    def get_model_version(self) -> str:
        return self.model_version
