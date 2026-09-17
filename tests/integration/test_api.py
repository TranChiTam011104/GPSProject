"""Integration tests for API."""
import pytest
from fastapi.testclient import TestClient


class TestAPI:
    """API integration tests."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        """Setup test client."""
        from src.api.main import app
        self.client = TestClient(app)

    def test_health_endpoint(self):
        """Test health check endpoint."""
        response = self.client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data

    def test_classify_endpoint_invalid_request(self):
        """Test classify endpoint with invalid request."""
        response = self.client.post(
            "/v1/classify/test_user",
            json={"stay_points": []}
        )
        # Should fail validation (empty stay_points)
        assert response.status_code in [400, 422]

    def test_metrics_endpoint(self):
        """Test metrics endpoint."""
        response = self.client.get("/metrics")
        assert response.status_code == 200
