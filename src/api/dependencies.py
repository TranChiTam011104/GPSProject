"""
FastAPI dependencies for dependency injection.
"""
from typing import Optional
from functools import lru_cache

from src.models.base import BaseClassifier
from src.models.heuristic import HeuristicClassifier
from src.models.cluster import ClusterClassifier
from src.config.settings import get_settings


# Global classifier instance
_classifier: Optional[BaseClassifier] = None
_current_model_version: str = "v1"


def get_classifier() -> BaseClassifier:
    """
    Get the current classifier instance.
    
    This is a dependency injection function for FastAPI.
    """
    global _classifier
    if _classifier is None:
        _classifier = _create_classifier()
    return _classifier


def get_model_version() -> str:
    """Get the current model version."""
    global _current_model_version
    return _current_model_version


def set_model_version(version: str):
    """
    Switch to a different model version.
    
    Args:
        version: Model version ('v1' or 'v2')
    """
    global _classifier, _current_model_version
    
    if version != _current_model_version:
        _current_model_version = version
        _classifier = _create_classifier(version)


def _create_classifier(version: Optional[str] = None) -> BaseClassifier:
    """
    Create a classifier based on version.
    
    Args:
        version: Model version ('v1' or 'v2')
        
    Returns:
        Classifier instance
    """
    settings = get_settings()
    
    if version is None:
        version = settings.model_version
    
    config = {
        "timezone": "Asia/Shanghai",
        "home_hour_start": 22,
        "home_hour_end": 6,
        "office_hour_start": 9,
        "office_hour_end": 18,
        "work_days": [0, 1, 2, 3, 4],
    }
    
    if version == "v2":
        config.update({
            "eps_meters": settings.dbscan_eps_meters,
            "min_samples": settings.dbscan_min_samples,
        })
        return ClusterClassifier(config)
    else:
        return HeuristicClassifier(config)


def reload_classifier():
    """Reload the classifier (e.g., after model update)."""
    global _classifier
    _classifier = _create_classifier()


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
