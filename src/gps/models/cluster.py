"""V2 classifier — DBSCAN cluster stay-points, then run the same v1 heuristic.

Implementation lives in Checkpoint 2 (Tuần 3). For now this stub returns a
:class:`HeuristicClassifier` so the dependency-injection path stays functional
end-to-end without raising ``ImportError``.
"""

from __future__ import annotations

from typing import Optional

from gps.models.heuristic import HeuristicClassifier


class ClusterClassifier(HeuristicClassifier):
    """Placeholder — full DBSCAN logic arrives in Checkpoint 2."""

    model_version = "v2-cluster-dbscan"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.eps_meters = float(self.config.get("eps_meters", 100.0))
        self.min_samples = int(self.config.get("min_samples", 3))

    def get_model_version(self) -> str:
        return self.model_version
