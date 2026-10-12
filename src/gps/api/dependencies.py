"""
FastAPI dependencies for dependency injection.

The classifier is built from ``get_settings()`` (``configs/{GPS_ENV}.yaml`` + env vars), so a
threshold changes in one place: the YAML file.
"""
from typing import Optional

from gps.models.base import BaseClassifier
from gps.models.heuristic import HeuristicClassifier
from gps.models.cluster import ClusterClassifier
from gps.config.settings import get_settings


# Global classifier instance and the version it was built for
_classifier: Optional[BaseClassifier] = None
_current_model_version: Optional[str] = None


def get_classifier() -> BaseClassifier:
    """
    Get the current classifier instance.

    This is a dependency injection function for FastAPI.
    """
    global _classifier
    if _classifier is None:
        _classifier = _create_classifier(get_model_version())
    return _classifier


def get_model_version() -> str:
    """Get the current model version ('v1' or 'v2'); defaults to ``GPS_MODEL_VERSION``."""
    return _current_model_version or get_settings().GPS_MODEL_VERSION


def set_model_version(version: str):
    """
    Switch to a different model version.

    Args:
        version: Model version ('v1' or 'v2')
    """
    global _classifier, _current_model_version

    if version != get_model_version():
        _current_model_version = version
        _classifier = _create_classifier(version)


def _create_classifier(version: str) -> BaseClassifier:
    """
    Create a classifier for a version, configured from settings.

    Args:
        version: Model version ('v1' or 'v2')

    Returns:
        Classifier instance
    """
    settings = get_settings()
    config = settings.classification.model_dump()

    if version == "v2":
        config.update({
            "eps_meters": settings.clustering.eps_meters,
            "min_samples": settings.clustering.min_samples,
        })
        return ClusterClassifier(config)
    return HeuristicClassifier(config)


def reload_classifier():
    """Reload the classifier (e.g., after model update)."""
    global _classifier
    _classifier = _create_classifier(get_model_version())


class ClassifierDepends:
    """
    Helper class for classifier dependency injection.

    Usage:
        @app.get("/classify")
        async def classify(depends: ClassifierDepends):
            classifier = depends.get_classifier()
    """

    @staticmethod
    def get_classifier() -> BaseClassifier:
        return get_classifier()

    @staticmethod
    def get_model_version() -> str:
        return get_model_version()
