"""Shadow deployment: the primary model answers, a second model runs after the response.

Only aggregates are kept (counters and latencies); home/office coordinates are never logged
or stored, so comparing the two models does not widen what the service retains about a user.
Evidence and promotion rule: ``docs/deployment/strategies.md``.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter
from dataclasses import dataclass, field

from gps.models.base import BaseClassifier, ClassificationResult, Location
from gps.utils.geo import haversine_meters

logger = logging.getLogger("gps.shadow")

# Same radius as the stay-point footprint and the classifier's support radius.
SAME_PLACE_RADIUS_M = 200.0

PLACE_TYPES = ("home", "office")


def _compare_place(primary: Location | None, shadow: Location | None) -> str:
    if primary is None and shadow is None:
        return "both_unknown"
    if primary is None:
        return "shadow_only"
    if shadow is None:
        return "primary_only"
    distance = haversine_meters(primary.lat, primary.lon, shadow.lat, shadow.lon)
    return "same_place" if distance <= SAME_PLACE_RADIUS_M else "different_place"


def compare_results(primary: ClassificationResult, shadow: ClassificationResult) -> dict[str, str]:
    """Per place type, how the shadow answer relates to the primary one (no coordinates)."""
    return {
        "home": _compare_place(primary.home, shadow.home),
        "office": _compare_place(primary.office, shadow.office),
    }


@dataclass
class ShadowStats:
    """Thread-safe aggregate of shadow comparisons since the process started."""

    requests: int = 0
    shadow_errors: int = 0
    outcomes: dict[str, Counter] = field(default_factory=lambda: {t: Counter() for t in PLACE_TYPES})
    primary_ms: list[float] = field(default_factory=list)
    shadow_ms: list[float] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, outcome: dict[str, str], primary_ms: float, shadow_ms: float) -> None:
        with self._lock:
            self.requests += 1
            for place_type, label in outcome.items():
                self.outcomes[place_type][label] += 1
            self.primary_ms.append(primary_ms)
            self.shadow_ms.append(shadow_ms)

    def record_error(self) -> None:
        with self._lock:
            self.shadow_errors += 1

    def summary(self) -> dict:
        with self._lock:
            out: dict = {"requests": self.requests, "shadow_errors": self.shadow_errors}
            for place_type in PLACE_TYPES:
                counts = self.outcomes[place_type]
                both = counts["same_place"] + counts["different_place"]
                out[place_type] = {
                    **counts,
                    "same_place_rate": counts["same_place"] / both if both else None,
                }
            out["latency_ms"] = {
                "primary_mean": _mean(self.primary_ms),
                "shadow_mean": _mean(self.shadow_ms),
            }
            return out


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


stats = ShadowStats()


def run_shadow(shadow_classifier: BaseClassifier, stay_points, primary: ClassificationResult,
               primary_ms: float) -> None:
    """Run the shadow model on the same stay-points and record how it compares to the primary.

    Runs as a background task: it never raises into the request, and a failure is counted.
    """
    try:
        start = time.perf_counter()
        shadow = shadow_classifier.predict(stay_points)
        shadow_ms = (time.perf_counter() - start) * 1000
        outcome = compare_results(primary, shadow)
        stats.record(outcome, primary_ms, shadow_ms)
        logger.info("shadow %s", json.dumps({
            "primary": primary.model_version, "shadow": shadow.model_version,
            "home": outcome["home"], "office": outcome["office"],
            "primary_ms": round(primary_ms, 2), "shadow_ms": round(shadow_ms, 2),
        }))
    except Exception:
        stats.record_error()
        logger.exception("shadow model failed")
