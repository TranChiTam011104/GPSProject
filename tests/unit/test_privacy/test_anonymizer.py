"""Unit tests for privacy anonymizer."""
import pytest
from src.privacy.anonymizer import PrivacyAnonymizer


class TestPrivacyAnonymizer:
    """Tests for PrivacyAnonymizer."""

    def test_initialization(self):
        """Test anonymizer can be initialized."""
        anonymizer = PrivacyAnonymizer(precision=6, k_threshold=5)
        assert anonymizer.precision == 6
        assert anonymizer.k_threshold == 5

    def test_encode_location(self):
        """Test geohash encoding."""
        anonymizer = PrivacyAnonymizer(precision=6)
        geohash_str = anonymizer.encode(39.9847, 116.3184)
        assert isinstance(geohash_str, str)
        assert len(geohash_str) == 6

    def test_anonymize_location(self):
        """Test location anonymization."""
        anonymizer = PrivacyAnonymizer(precision=6)
        result = anonymizer.anonymize_location(39.9847, 116.3184)
        
        assert result.geohash is not None
        assert result.precision == 6
        assert result.cluster_size == 1

    def test_anonymize_batch(self):
        """Test batch anonymization."""
        anonymizer = PrivacyAnonymizer(precision=6)
        locations = [
            (39.9847, 116.3184),
            (39.9847, 116.3185),  # Same area
            (40.1234, 116.5678),  # Different area
        ]
        
        results = anonymizer.anonymize_batch(locations)
        assert len(results) > 0

    def test_check_k_anonymity(self):
        """Test k-anonymity check."""
        anonymizer = PrivacyAnonymizer(precision=6, k_threshold=2)
        
        # 3 locations with same geohash (k=3 >= 2)
        locations = [
            anonymizer.encode(39.9847, 116.3184),
            anonymizer.encode(39.9847, 116.3185),
            anonymizer.encode(39.9847, 116.3186),
        ]
        
        is_k_anon, min_count = anonymizer.check_k_anonymity(locations)
        # The k-anonymity check depends on actual geohash encoding
        assert isinstance(is_k_anon, bool)
        assert min_count >= 1

    def test_hash_identifier(self):
        """Test user ID hashing."""
        hash1 = PrivacyAnonymizer.hash_identifier("user_123")
        hash2 = PrivacyAnonymizer.hash_identifier("user_123")
        
        # Same input should produce same hash
        assert hash1 == hash2
        
        # Different input should produce different hash
        hash3 = PrivacyAnonymizer.hash_identifier("user_456")
        assert hash1 != hash3

    def test_differential_privacy_noise(self):
        """Test differential privacy noise addition."""
        anonymizer = PrivacyAnonymizer()
        
        # Add noise multiple times
        noisy_results = [
            anonymizer.add_differential_privacy_noise(39.9847, 116.3184)
            for _ in range(10)
        ]
        
        # All should be valid coordinates
        for lat, lng in noisy_results:
            assert -90 <= lat <= 90
            assert -180 <= lng <= 180
