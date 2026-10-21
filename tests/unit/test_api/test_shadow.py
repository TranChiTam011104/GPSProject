"""Shadow deployment: v1 answers, v2 is only compared, and no coordinates are kept."""
import json

import pytest
from fastapi.testclient import TestClient

from gps.api import dependencies, shadow
from gps.config import settings as settings_module

HOME = {"lat": 39.9847, "lon": 116.3184}
OFFICE = {"lat": 40.0043, "lon": 116.3263}


def stay(place, arrival, departure):
    return {**place, "arrival_time": arrival, "departure_time": departure}


STAYS = [
    stay(HOME, "2008-10-22T14:30:00", "2008-10-22T22:45:00"),
    stay(HOME, "2008-10-23T14:30:00", "2008-10-23T22:45:00"),
    stay(OFFICE, "2008-10-23T01:00:00", "2008-10-23T10:30:00"),
    stay(OFFICE, "2008-10-24T01:00:00", "2008-10-24T10:30:00"),
]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GPS_MODEL_VERSION", "v1")
    monkeypatch.setenv("GPS_SHADOW_MODEL_VERSION", "v2")
    settings_module.get_settings.cache_clear()
    monkeypatch.setattr(dependencies, "_classifier", None)
    monkeypatch.setattr(dependencies, "_current_model_version", None)
    monkeypatch.setattr(dependencies, "_shadow_classifier", None)
    monkeypatch.setattr(shadow, "stats", shadow.ShadowStats())
    from gps.api.main import app
    yield TestClient(app)
    settings_module.get_settings.cache_clear()


def test_primary_answers_and_shadow_is_recorded(client):
    response = client.post("/v1/classify/010", json={"stay_points": STAYS})
    assert response.status_code == 200
    assert response.json()["model_version"] == "v1-heuristic"

    summary = client.get("/v1/shadow/summary").json()
    assert summary["primary"] == "v1" and summary["shadow"] == "v2"
    assert summary["requests"] == 1 and summary["shadow_errors"] == 0
    assert summary["home"]["same_place"] == 1
    assert summary["home"]["same_place_rate"] == 1.0


def test_summary_and_logs_hold_no_coordinates(client, caplog):
    caplog.set_level("INFO", logger="gps.shadow")
    client.post("/v1/classify/010", json={"stay_points": STAYS})
    text = json.dumps(client.get("/v1/shadow/summary").json()) + caplog.text
    assert "39.98" not in text and "116.31" not in text


def test_shadow_failure_does_not_break_the_response(client, monkeypatch):
    class Boom:
        def predict(self, _):
            raise RuntimeError("shadow down")

    monkeypatch.setattr(dependencies, "_shadow_classifier", Boom())
    monkeypatch.setattr(dependencies, "_shadow_version", "v2")
    response = client.post("/v1/classify/010", json={"stay_points": STAYS})
    assert response.status_code == 200
    assert client.get("/v1/shadow/summary").json()["shadow_errors"] == 1


def test_shadow_off_by_default(monkeypatch):
    monkeypatch.setenv("GPS_SHADOW_MODEL_VERSION", "")
    settings_module.get_settings.cache_clear()
    monkeypatch.setattr(dependencies, "_shadow_classifier", None)
    assert dependencies.get_shadow_classifier() is None
    settings_module.get_settings.cache_clear()


def test_shadow_same_as_primary_is_ignored(monkeypatch):
    monkeypatch.setenv("GPS_MODEL_VERSION", "v1")
    monkeypatch.setenv("GPS_SHADOW_MODEL_VERSION", "v1")
    settings_module.get_settings.cache_clear()
    monkeypatch.setattr(dependencies, "_current_model_version", None)
    assert dependencies.get_shadow_classifier() is None
    settings_module.get_settings.cache_clear()


def test_models_endpoint_lists_versions_and_parameters(client):
    body = client.get("/v1/models").json()
    assert body["active"] == "v1" and body["shadow"] == "v2"
    assert body["versions"]["v1"]["model_version"] == "v1-heuristic"
    assert body["versions"]["v2"]["model_version"] == "v2-cluster-dbscan"
    assert body["versions"]["v2"]["params"]["eps_meters"] == 150.0
    assert body["versions"]["v1"]["params"]["min_window_minutes"] == 240.0
