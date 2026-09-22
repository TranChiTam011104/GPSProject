"""GPS Home/Office/POI Inference — Track B1 (MLE Intern).

Layered package layout (src layout):
    gps.config     — Pydantic settings + YAML/env hybrid
    gps.utils      — Shared utilities (geo, time)
    gps.data       — Ingestion, cleaning, timezone (Checkpoint 1 W1)
    gps.features   — Stay-point detection, clustering, geohash/h3
    gps.models     — Heuristic (v1) + Cluster (v2) classifiers
    gps.ml         — Model registry / versioning
    gps.pipeline   — End-to-end orchestration
    gps.serving    — Sync / async / batch serving
    gps.api        — FastAPI app + OpenAPI spec (Checkpoint 1 W2)
    gps.privacy    — Anonymizer (k-anonymity, geohash)
    gps.monitoring — Metrics, logger, drift
"""

__version__ = "0.1.0"
