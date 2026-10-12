"""V2 classifier — DBSCAN groups stay-points into places, then the v1 time windows score each place.

Algorithm (Checkpoint 2; evidence in notebooks/14_place_clustering.ipynb):

1. Drop stay-points shorter than ``min_duration_minutes`` and convert them to local time, as v1.
2. DBSCAN on the stays' centres (haversine, ``eps_meters``, ``min_samples`` counting stays).
   Noise stays are not dropped: each one is a place of its own, so no data is lost and a place
   seen once is handled by the "unknown" rule below.
3. Score each place by the minutes all its stays spend inside the home / office window
   (same windows and same ``window_minutes`` as v1). The winner per type is the place with the
   most window minutes; ties go to the longer total stay, then to the earlier first arrival.
4. Location = duration-weighted centre of the place's stays; confidence = winner's window
   minutes / window minutes of all places of that type.
5. A winner is found only when it has at least ``min_window_minutes`` inside the window and
   window minutes on at least ``min_window_days`` distinct days (nights for home, Mon–Fri for
   office); otherwise the type is "unknown" (``too_few_window_minutes`` / ``one_off_place``).
   ``PlaceStatus.support`` holds those days.
6. POIs are the places that touch neither window, ranked by total stay duration — the same
   grouping as home and office, instead of v1's geohash cells.

Chosen ``eps_meters = 150``, ``min_samples = 2``: split-half stability is flat from 100 m on
(55–68%); 150 m is the smallest radius where home and office both reach the stability of a
200 m area (62% / 62% against v1's 41% / 42%) while home and office are merged into one place
no more often than they really sit within 200 m of each other (29% against 26–28%). Counting
distinct days in ``min_samples`` did not help. With ``min_samples = 2`` every stay that has a
neighbour is a core point, so DBSCAN has no border points and its result does not depend on
the input order.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from geohash2 import encode as geohash_encode
from sklearn.cluster import DBSCAN

from gps.data.timezone import local_times
from gps.models.base import ClassificationResult, Location, PlaceStatus, coerce_stay_points
from gps.models.heuristic import HeuristicClassifier
from gps.utils.geo import EARTH_RADIUS_KM


def place_labels(lats, lons, eps_meters: float, min_samples: int) -> np.ndarray:
    """Place id per stay: DBSCAN clusters, then each noise stay as a place of its own (ids 0..K-1)."""
    if len(lats) == 0:
        return np.zeros(0, dtype=int)
    coords = np.radians(np.column_stack([lats, lons]))
    labels = DBSCAN(eps=eps_meters / (EARTH_RADIUS_KM * 1000.0), min_samples=min_samples,
                    metric="haversine", algorithm="ball_tree").fit(coords).labels_.copy()
    noise = labels < 0
    labels[noise] = labels.max(initial=-1) + 1 + np.arange(noise.sum())
    return labels


class ClusterClassifier(HeuristicClassifier):
    """Home/office classifier on DBSCAN places (model v2)."""

    model_version = "v2-cluster-dbscan"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.eps_meters = float(self.config.get("eps_meters", 150.0))
        self.min_samples = int(self.config.get("min_samples", 2))
        self.min_window_days = int(self.config.get("min_window_days", 2))

    def predict(self, stay_points: Iterable[dict]) -> ClassificationResult:
        sps = [sp for sp in coerce_stay_points(stay_points)
               if sp.duration_minutes >= self.min_duration_minutes]
        lats, lons = [sp.lat for sp in sps], [sp.lon for sp in sps]
        arrivals = local_times([sp.arrival_time for sp in sps], lats, lons)
        departures = local_times([sp.departure_time for sp in sps], lats, lons)
        labels = place_labels(lats, lons, self.eps_meters, self.min_samples)

        places: dict[int, dict] = {}
        for sp, arr, dep, label in zip(sps, arrivals, departures, labels, strict=True):
            home_min, office_min = self.window_minutes(arr, dep)
            home_days, office_days = self.window_days(arr, dep)
            p = places.setdefault(int(label), {"stays": [], "home": 0.0, "office": 0.0,
                                               "home_days": set(), "office_days": set()})
            p["stays"].append(sp)
            p["home"] += home_min
            p["office"] += office_min
            p["home_days"] |= home_days
            p["office_days"] |= office_days
        places_list = list(places.values())

        home, home_status = self._pick_place(places_list, "home")
        office, office_status = self._pick_place(places_list, "office")
        pois = self._top_poi_places([p for p in places_list if p["home"] == 0 and p["office"] == 0])

        return ClassificationResult(
            user_id="",
            locations=[loc for loc in (home, office) if loc] + pois,
            home=home,
            office=office,
            home_status=home_status,
            office_status=office_status,
            pois=pois,
            model_version=self.model_version,
        )

    # ── Internals ────────────────────────────────────────────────────────────

    def _pick_place(self, places: list[dict], label: str) -> tuple[Location | None, PlaceStatus]:
        candidates = [p for p in places if p[label] > 0]
        if not candidates:
            return None, PlaceStatus()
        total = sum(p[label] for p in candidates)
        best = max(candidates, key=lambda p: (p[label], _total_duration(p),
                                              -min(sp.arrival_time for sp in p["stays"]).timestamp()))
        minutes, days = best[label], len(best[f"{label}_days"])
        if minutes < self.min_window_minutes:
            return None, PlaceStatus("unknown", "too_few_window_minutes", minutes, days)
        if days < self.min_window_days:
            return None, PlaceStatus("unknown", "one_off_place", minutes, days)
        return self._place_location(best, label, min(1.0, minutes / total)), PlaceStatus("found", None, minutes, days)

    def _top_poi_places(self, places: list[dict]) -> list[Location]:
        total = sum(_total_duration(p) for p in places) or 1.0
        ranked = sorted(places, key=_total_duration, reverse=True)[: self.top_poi_n]
        return [self._place_location(p, "poi", min(1.0, _total_duration(p) / total)) for p in ranked]

    def _place_location(self, place: dict, label: str, confidence: float) -> Location:
        stays = place["stays"]
        weights = [sp.duration_minutes for sp in stays]
        lat = float(np.average([sp.lat for sp in stays], weights=weights))
        lon = float(np.average([sp.lon for sp in stays], weights=weights))
        altitudes = [sp.altitude_m for sp in stays if sp.altitude_m]
        arrivals = [sp.arrival_time for sp in stays]
        return Location(
            lat=lat,
            lon=lon,
            location_type=label,
            confidence=confidence,
            visit_count=len(stays),
            duration_minutes=_total_duration(place),
            altitude_m=float(np.mean(altitudes)) if altitudes else 0.0,
            first_seen=min(arrivals),
            last_seen=max(arrivals),
            geohash=geohash_encode(lat, lon, precision=self.geohash_precision),
        )


def _total_duration(place: dict) -> float:
    return sum(sp.duration_minutes for sp in place["stays"])
