"""Integration tests for the API: the classify endpoint takes stay-points only."""
import pytest
from fastapi.testclient import TestClient

HOME = {"lat": 39.9847, "lon": 116.3184}
OFFICE = {"lat": 40.0043, "lon": 116.3263}


def stay(place, arrival, departure, **extra):
    return {**place, "arrival_time": arrival, "departure_time": departure, **extra}


class TestAPI:
    """API integration tests."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        from gps.api.main import app
        self.client = TestClient(app)

    def classify(self, stay_points):
        return self.client.post("/v1/classify/010", json={"stay_points": stay_points})

    def test_health_endpoint(self):
        response = self.client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data

    def test_metrics_endpoint(self):
        assert self.client.get("/metrics").status_code == 200

    def test_classify_accepts_pipeline_shaped_stay_points(self):
        response = self.classify([
            stay(HOME, "2008-10-22T14:30:00", "2008-10-22T22:45:00", observed_minutes=480.0, altitude_m=50.0),
            stay(HOME, "2008-10-23T14:30:00", "2008-10-23T22:45:00"),
            stay(OFFICE, "2008-10-23T01:00:00", "2008-10-23T10:30:00"),
            stay(OFFICE, "2008-10-24T01:00:00", "2008-10-24T10:30:00"),
        ])
        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == "010"
        assert body["home"]["location_type"] == "home"
        assert body["office"]["location_type"] == "office"
        assert body["home_status"]["status"] == "found"
        assert body["home_status"]["support"] == 2
        assert body["office_status"]["reason"] is None

    def test_one_off_stay_is_unknown_with_reason_and_evidence(self):
        body = self.classify([stay(HOME, "2008-10-23T14:30:00", "2008-10-23T22:45:00")]).json()
        assert body["home"] is None
        assert body["home_status"] == {"status": "unknown", "reason": "one_off_place",
                                       "window_minutes": 495.0, "support": 1}
        assert body["office_status"]["reason"] == "no_candidate"

    def test_tz_aware_and_gmt_requests_give_the_same_answer(self):
        gmt = self.classify([stay(HOME, f"2008-10-{d}T14:30:00", f"2008-10-{d}T22:45:00") for d in (22, 23)]).json()
        local = self.classify([stay(HOME, f"2008-10-{d}T22:30:00+08:00", f"2008-10-{d + 1}T06:45:00+08:00")
                               for d in (22, 23)]).json()
        assert gmt["locations"]
        assert gmt["locations"] == local["locations"]

    @pytest.mark.parametrize("stay_points", [
        [],                                                                          # nothing to classify
        [{**HOME, "timestamp": "2008-10-23T14:30:00"}],                              # raw GPS point
        [stay(HOME, "2008-10-23T22:45:00", "2008-10-23T14:30:00")],                  # departure before arrival
        [stay(HOME, "2008-10-23T14:30:00", "2008-10-23T15:30:00", observed_minutes=90)],  # observed > duration
    ])
    def test_invalid_requests_are_rejected(self, stay_points):
        assert self.classify(stay_points).status_code == 422
