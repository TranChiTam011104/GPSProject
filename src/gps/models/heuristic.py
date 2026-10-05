"""V1 baseline classifier — apply time-of-day heuristic on each stay-point.

Algorithm (per Checkpoint 1 / Tuần 1):

1. Drop stay-points shorter than ``min_duration_minutes``.
2. Classify each stay-point by the local hour of its arrival. Times arrive as naive
   GMT (GeoLife convention); local time comes from the time zone of the stay's
   location, as in the pipeline (notebooks/09_timezone_by_location.ipynb).
   - ``home_hour_start..home_hour_end`` (wraps midnight) → ``"home"``
   - ``office_hour_start..office_hour_end`` on a work-day → ``"office"``
   - otherwise → ``"poi"``
3. Aggregate buckets (using rounded lat/lon keys) to suppress GPS jitter.
4. Pick the highest-dwell bucket per type as the winner.
5. Confidence = share of total ``type``-dwell time captured by the winner.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime

from geohash2 import encode as geohash_encode

from gps.data.timezone import local_times
from gps.models.base import (
    BaseClassifier,
    ClassificationResult,
    Location,
    coerce_stay_points,
)


class HeuristicClassifier(BaseClassifier):
    """Baseline home/office classifier (model v1)."""

    model_version = "v1-heuristic"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        # ── Exposed attributes for unit tests (and runtime tuning) ──────────
        self.home_hour_start: int = int(self.config.get("home_hour_start", 22))
        self.home_hour_end: int = int(self.config.get("home_hour_end", 6))
        self.office_hour_start: int = int(self.config.get("office_hour_start", 9))
        self.office_hour_end: int = int(self.config.get("office_hour_end", 18))
        self.work_days: tuple = tuple(self.config.get("work_days", (0, 1, 2, 3, 4)))
        self.min_duration_minutes: float = float(self.config.get("min_duration_minutes", 30.0))
        self.geohash_precision: int = int(self.config.get("geohash_precision", 6))
        self.top_poi_n: int = int(self.config.get("top_poi_n", 5))
        self._bucket_decimals = 6

    # ── Public API ───────────────────────────────────────────────────────────

    def get_model_version(self) -> str:
        return self.model_version

    def predict(self, stay_points: Iterable[dict]) -> ClassificationResult:
        sps = [sp for sp in coerce_stay_points(stay_points)
               if sp.duration_minutes >= self.min_duration_minutes]
        # Nhãn tính một lần mỗi request, không lưu vào self: API dùng chung 1 classifier.
        arrivals = local_times([sp.arrival_time for sp in sps], [sp.lat for sp in sps], [sp.lon for sp in sps])
        labelled = [(sp, self._label(local)) for sp, local in zip(sps, arrivals, strict=True)]

        home = self._pick_winner(labelled, label="home")
        office = self._pick_winner(labelled, label="office")
        exclude_keys = {(loc.lat, loc.lon) for loc in (home, office) if loc}
        pois = self._pick_top_pois(labelled, exclude_keys)

        all_locs: list[Location] = []
        if home:
            all_locs.append(home)
        if office:
            all_locs.append(office)
        all_locs.extend(pois)

        return ClassificationResult(
            user_id="",
            locations=all_locs,
            home=home,
            office=office,
            pois=pois,
            model_version=self.model_version,
        )

    # ── Predicates (unit-tested directly) ────────────────────────────────────

    def _is_home_time(self, dt: datetime) -> bool:
        return _hour_in_range(dt.hour, self.home_hour_start, self.home_hour_end)

    def _is_office_time(self, dt: datetime) -> bool:
        return dt.weekday() in self.work_days and _hour_in_range(
            dt.hour, self.office_hour_start, self.office_hour_end
        )

    # ── Internals ────────────────────────────────────────────────────────────

    def _label(self, local_arrival: datetime) -> str:
        if self._is_home_time(local_arrival):
            return "home"
        if self._is_office_time(local_arrival):
            return "office"
        return "poi"

    def _bucket_key(self, sp):
        return (round(sp.lat, self._bucket_decimals), round(sp.lon, self._bucket_decimals))

    def _aggregate(self, labelled, target_label):
        """Return list of (key, total_duration_min, visit_count, first_seen, last_seen, mean_alt)."""
        agg: dict[tuple[float, float], dict] = defaultdict(lambda: {
            "duration": 0.0, "visits": 0,
            "first_seen": None, "last_seen": None, "altitude_sum": 0.0, "altitude_n": 0,
        })
        for sp, label in labelled:
            if label != target_label:
                continue
            key = self._bucket_key(sp)
            entry = agg[key]
            entry["duration"] += sp.duration_minutes
            entry["visits"] += 1
            ts = sp.arrival_time
            if entry["first_seen"] is None or ts < entry["first_seen"]:
                entry["first_seen"] = ts
            if entry["last_seen"] is None or ts > entry["last_seen"]:
                entry["last_seen"] = ts
            if sp.altitude_m:
                entry["altitude_sum"] += sp.altitude_m
                entry["altitude_n"] += 1
        return [
            (
                k,
                v["duration"],
                v["visits"],
                v["first_seen"],
                v["last_seen"],
                (v["altitude_sum"] / v["altitude_n"]) if v["altitude_n"] else 0.0,
            )
            for k, v in agg.items()
        ]

    def _pick_winner(self, labelled, label: str) -> Location | None:
        scored = self._aggregate(labelled, label)
        if not scored:
            return None
        total = sum(d for _, d, *_ in scored) or 1.0
        scored.sort(key=lambda x: x[1], reverse=True)
        (lat, lon), duration, visits, first_seen, last_seen, mean_alt = scored[0]
        return Location(
            lat=lat,
            lon=lon,
            location_type=label,
            confidence=min(1.0, duration / total),
            visit_count=visits,
            duration_minutes=duration,
            altitude_m=mean_alt,
            first_seen=first_seen,
            last_seen=last_seen,
            geohash=geohash_encode(lat, lon, precision=self.geohash_precision),
        )

    def _pick_top_pois(self, labelled, exclude_keys) -> list[Location]:
        agg: dict[str, dict] = {}
        for sp, label in labelled:
            if label != "poi":
                continue
            key = self._bucket_key(sp)
            if key in exclude_keys:
                continue
            gh = geohash_encode(sp.lat, sp.lon, precision=self.geohash_precision)
            if gh not in agg:
                agg[gh] = {
                    "lat": sp.lat, "lon": sp.lon,
                    "duration": 0.0, "visits": 0,
                    "altitude_sum": 0.0, "altitude_n": 0,
                    "first_seen": None, "last_seen": None,
                }
            entry = agg[gh]
            entry["duration"] += sp.duration_minutes
            entry["visits"] += 1
            ts = sp.arrival_time
            if entry["first_seen"] is None or ts < entry["first_seen"]:
                entry["first_seen"] = ts
            if entry["last_seen"] is None or ts > entry["last_seen"]:
                entry["last_seen"] = ts
            if sp.altitude_m:
                entry["altitude_sum"] += sp.altitude_m
                entry["altitude_n"] += 1

        scored = sorted(agg.items(), key=lambda kv: kv[1]["duration"], reverse=True)
        if not scored:
            return []
        total = sum(v["duration"] for _, v in scored) or 1.0
        pois: list[Location] = []
        for gh, info in scored[: self.top_poi_n]:
            mean_alt = (
                info["altitude_sum"] / info["altitude_n"] if info["altitude_n"] else 0.0
            )
            pois.append(
                Location(
                    lat=info["lat"],
                    lon=info["lon"],
                    location_type="poi",
                    confidence=min(1.0, info["duration"] / total),
                    visit_count=info["visits"],
                    duration_minutes=info["duration"],
                    altitude_m=mean_alt,
                    first_seen=info["first_seen"],
                    last_seen=info["last_seen"],
                    geohash=gh,
                )
            )
        return pois


def _hour_in_range(hour: int, start: int, end: int) -> bool:
    """Half-open range [start, end) with wrap-around midnight support."""
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end
