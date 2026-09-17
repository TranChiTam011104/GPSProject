"""Unit tests for cluster-based classifier."""
import pytest
from src.models.cluster import ClusterClassifier


class TestClusterClassifier:
    """Tests for ClusterClassifier."""

    def test_initialization(self):
        """Test classifier can be initialized."""
        classifier = ClusterClassifier()
        assert classifier.eps_meters == 100.0
        assert classifier.min_samples == 3

    def test_initialization_with_config(self):
        """Test with custom config."""
        config = {
            "eps_meters": 200.0,
            "min_samples": 5
        }
        classifier = ClusterClassifier(config)
        assert classifier.eps_meters == 200.0

    def test_model_version(self):
        """Test model version identifier."""
        classifier = ClusterClassifier()
        assert classifier.get_model_version() == "v2-cluster-dbscan"
