"""The API builds its classifier from settings (configs/{GPS_ENV}.yaml), not from constants."""

import pytest

from gps.api import dependencies
from gps.config import settings as settings_module
from gps.models.cluster import ClusterClassifier
from gps.models.heuristic import HeuristicClassifier


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    (tmp_path / "dev.yaml").write_text(
        "classification:\n"
        "  home_hour_start: 21\n"
        "  min_window_minutes: 123.0\n"
        "  work_days: [0, 1]\n"
        "clustering:\n"
        "  eps_meters: 77.0\n"
        "  min_samples: 4\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "CONFIG_DIR", tmp_path)
    monkeypatch.delenv("GPS_ENV", raising=False)
    monkeypatch.delenv("GPS_MODEL_VERSION", raising=False)
    settings_module.get_settings.cache_clear()
    monkeypatch.setattr(dependencies, "_classifier", None)
    monkeypatch.setattr(dependencies, "_current_model_version", None)
    yield tmp_path
    settings_module.get_settings.cache_clear()


def test_v1_classifier_uses_yaml_values(config_dir):
    classifier = dependencies.get_classifier()
    assert isinstance(classifier, HeuristicClassifier)
    assert classifier.home_hour_start == 21
    assert classifier.min_window_minutes == 123.0
    assert classifier.work_days == (0, 1)


def test_v2_classifier_gets_clustering_params(config_dir):
    dependencies.set_model_version("v2")
    classifier = dependencies.get_classifier()
    assert isinstance(classifier, ClusterClassifier)
    assert (classifier.eps_meters, classifier.min_samples) == (77.0, 4)
    assert classifier.home_hour_start == 21


def test_model_version_defaults_to_settings(config_dir, monkeypatch):
    monkeypatch.setenv("GPS_MODEL_VERSION", "v2")
    settings_module.get_settings.cache_clear()
    assert dependencies.get_model_version() == "v2"
    assert isinstance(dependencies.get_classifier(), ClusterClassifier)
