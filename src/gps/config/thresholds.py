"""Thin re-exports for legacy callers.

New code should use :mod:`gps.config.settings` and the dataclasses live in
:mod:`gps.models.base` (Location, ClassificationResult).
"""

from __future__ import annotations

# Re-export the central Pydantic config so legacy imports keep working.
from gps.config.settings import (  # noqa: F401
    Settings,
    get_settings,
    StayPointConfig,
    ClusteringConfig,
    ClassificationConfig,
    APIConfig,
)
