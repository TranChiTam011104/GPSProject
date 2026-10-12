"""V1 baseline classifier — time-in-window heuristic applied to each stay-point.

Algorithm (per Checkpoint 1 / Tuần 1; evidence in notebooks/12_home_office_time_windows.ipynb):

1. Drop stay-points shorter than ``min_duration_minutes``.
2. Convert each stay to local time. Times arrive as naive GMT (GeoLife convention);
   local time comes from the time zone of the stay's location, as in the pipeline
   (notebooks/09_timezone_by_location.ipynb).
3. Score each stay by the minutes it spends inside each daily window:
   - home: ``home_hour_start..home_hour_end`` (wraps midnight), every day;
   - office: ``office_hour_start..office_hour_end``, only on ``work_days``.
   A stay arriving at 20:00 and staying the night counts as home; the arrival hour alone
   would miss it.
4. The winner of a type is the stay with the most minutes in that type's window. Ties
   (full nights tie often) go to the longer stay, then to the earlier arrival.
5. Stays are scored one by one, with no merging of nearby stays (v2 does that with DBSCAN).
6. Confidence = winner's window minutes / all stays' window minutes of that type.
7. A winner is reported as found only when it has at least ``min_window_minutes`` inside
   the window and at least ``min_support`` candidates (itself included) within
   ``support_radius_m``; otherwise the type is "unknown" with a reason
   (notebooks/13_minimum_evidence.ipynb). Counting nearby candidates does not merge
   stays or change the winner.
8. POIs are the stays that touch neither window, grouped by geohash.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

from geohash2 import encode as geohash_encode

from gps.data.timezone import local_times
from gps.models.base import (
    BaseClassifier,
    ClassificationResult,
    Location,
    PlaceStatus,
    coerce_stay_points,
)
from gps.utils.geo import haversine_meters

_DAY = timedelta(days=1)


class HeuristicClassifier(BaseClassifier):
    """Baseline home/office classifier (model v1)."""

    model_version = "v1-heuristic"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        # ── Exposed attributes for unit tests (and runtime tuning) ──────────
        self.home_hour_start: int = int(self.config.get("home_hour_start", 22))
        self.home_hour_end: int = int(self.config.get("home_hour_end", 8))
        self.office_hour_start: int = int(self.config.get("office_hour_start", 9))
        self.office_hour_end: int = int(self.config.get("office_hour_end", 18))
        self.work_days: tuple = tuple(self.config.get("work_days", (0, 1, 2, 3, 4)))
        self.min_duration_minutes: float = float(self.config.get("min_duration_minutes", 30.0))
        self.geohash_precision: int = int(self.config.get("geohash_precision", 6))
        self.top_poi_n: int = int(self.config.get("top_poi_n", 5))
        self.min_window_minutes: float = float(self.config.get("min_window_minutes", 240.0))
        self.min_support: int = int(self.config.get("min_support", 2))
        self.support_radius_m: float = float(self.config.get("support_radius_m", 200.0))

    # ── Public API ───────────────────────────────────────────────────────────

    def get_model_version(self) -> str:
        return self.model_version

    def predict(self, stay_points: Iterable[dict]) -> ClassificationResult:
        sps = [sp for sp in coerce_stay_points(stay_points)
               if sp.duration_minutes >= self.min_duration_minutes]
        lats, lons = [sp.lat for sp in sps], [sp.lon for sp in sps]
        arrivals = local_times([sp.arrival_time for sp in sps], lats, lons)
        departures = local_times([sp.departure_time for sp in sps], lats, lons)
        # (stay, home minutes, office minutes); computed once per request, not stored on self
        # because the API shares one classifier between requests.
        scored = [(sp, *self.window_minutes(arr, dep)) for sp, arr, dep in zip(sps, arrivals, departures, strict=True)]

        home, home_status = self._pick_winner(scored, "home", 1)
        office, office_status = self._pick_winner(scored, "office", 2)
        pois = self._pick_top_pois([sp for sp, home_min, office_min in scored if home_min == 0 and office_min == 0])

        all_locs = [loc for loc in (home, office) if loc] + pois
        return ClassificationResult(
            user_id="",
            locations=all_locs,
            home=home,
            office=office,
            home_status=home_status,
            office_status=office_status,
            pois=pois,
            model_version=self.model_version,
        )

    def window_minutes(self, local_arrival: datetime, local_departure: datetime) -> tuple[float, float]:
        """(home, office) minutes of a stay inside the daily windows, in local wall-clock time."""
        home = office = 0.0
        day = datetime.combine(local_arrival.date() - _DAY, datetime.min.time())
        while day <= local_departure:
            home += _overlap_minutes(local_arrival, local_departure, day, self.home_hour_start, self.home_hour_end)
            if day.weekday() in self.work_days:
                office += _overlap_minutes(local_arrival, local_departure, day, self.office_hour_start,
                                           self.office_hour_end)
            day += _DAY
        return home, office

    # ── Internals ────────────────────────────────────────────────────────────

    def _pick_winner(self, scored, label: str, column: int) -> tuple[Location | None, PlaceStatus]:
        """``column`` is the position of the type's minutes after the stay (1 = home, 2 = office)."""
        candidates = [(row[0], row[column]) for row in scored if row[column] > 0]
        if not candidates:
            return None, PlaceStatus()
        total = sum(minutes for _, minutes in candidates)
        sp, minutes = max(candidates, key=lambda c: (c[1], c[0].duration_minutes, -c[0].arrival_time.timestamp()))
        support = sum(1 for other, _ in candidates
                      if haversine_meters(sp.lat, sp.lon, other.lat, other.lon) <= self.support_radius_m)
        if minutes < self.min_window_minutes:
            return None, PlaceStatus("unknown", "too_few_window_minutes", minutes, support)
        if support < self.min_support:
            return None, PlaceStatus("unknown", "one_off_place", minutes, support)
        location = Location(
            lat=sp.lat,
            lon=sp.lon,
            location_type=label,
            confidence=min(1.0, minutes / total),
            visit_count=1,
            duration_minutes=sp.duration_minutes,
            altitude_m=sp.altitude_m or 0.0,
            first_seen=sp.arrival_time,
            last_seen=sp.arrival_time,
            geohash=geohash_encode(sp.lat, sp.lon, precision=self.geohash_precision),
        )
        return location, PlaceStatus("found", None, minutes, support)

    def _pick_top_pois(self, sps) -> list[Location]:
        agg: dict[str, dict] = {}
        for sp in sps:
            gh = geohash_encode(sp.lat, sp.lon, precision=self.geohash_precision)
            entry = agg.setdefault(gh, {
                "lat": sp.lat, "lon": sp.lon, "duration": 0.0, "visits": 0,
                "first_seen": sp.arrival_time, "last_seen": sp.arrival_time,
                "altitude_sum": 0.0, "altitude_n": 0,
            })
            entry["duration"] += sp.duration_minutes
            entry["visits"] += 1
            entry["first_seen"] = min(entry["first_seen"], sp.arrival_time)
            entry["last_seen"] = max(entry["last_seen"], sp.arrival_time)
            if sp.altitude_m:
                entry["altitude_sum"] += sp.altitude_m
                entry["altitude_n"] += 1

        total = sum(v["duration"] for v in agg.values()) or 1.0
        scored = sorted(agg.items(), key=lambda kv: kv[1]["duration"], reverse=True)
        return [
            Location(
                lat=info["lat"],
                lon=info["lon"],
                location_type="poi",
                confidence=min(1.0, info["duration"] / total),
                visit_count=info["visits"],
                duration_minutes=info["duration"],
                altitude_m=info["altitude_sum"] / info["altitude_n"] if info["altitude_n"] else 0.0,
                first_seen=info["first_seen"],
                last_seen=info["last_seen"],
                geohash=gh,
            )
            for gh, info in scored[: self.top_poi_n]
        ]


def _overlap_minutes(arrival: datetime, departure: datetime, day: datetime, start: int, end: int) -> float:
    """Minutes of [arrival, departure) inside the window that opens at ``start`` o'clock on ``day``
    and closes at ``end`` o'clock (the next day when ``end <= start``)."""
    opens = day + timedelta(hours=start)
    closes = day + timedelta(hours=end if end > start else end + 24)
    return max(0.0, (min(departure, closes) - max(arrival, opens)).total_seconds() / 60.0)
