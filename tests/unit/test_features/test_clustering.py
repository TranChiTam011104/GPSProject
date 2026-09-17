"""Unit tests for geohash encoder."""
import pytest
from src.features.geohash import GeohashEncoder, calculate_k_anonymity


class TestGeohashEncoder:
    """Tests for GeohashEncoder."""

    def test_initialization(self):
        """Test encoder initialization."""
        encoder = GeohashEncoder(precision=6)
        assert encoder.precision == 6

    def test_encode_location(self):
        """Test encoding a location."""
        encoder = GeohashEncoder(precision=6)
        result = encoder.encode(39.9847, 116.3184)
        assert isinstance(result, str)
        assert len(result) == 6

    def test_different_precisions(self):
        """Test encoding at different precisions."""
        for precision in [4, 5, 6, 7, 8]:
            encoder = GeohashEncoder(precision=precision)
            result = encoder.encode(39.9847, 116.3184)
            assert len(result) == precision

    def test_neighborhood_similar_encoding(self):
        """Test nearby locations have similar geohash."""
        encoder = GeohashEncoder(precision=8)
        
        # Two very close locations
        gh1 = encoder.encode(39.9847, 116.3184)
        gh2 = encoder.encode(39.9848, 116.3185)
        
        # Should share prefix
        assert gh1[:5] == gh2[:5]

    def test_far_locations_different(self):
        """Test far locations have different geohash."""
        encoder = GeohashEncoder(precision=6)
        
        # Beijing vs Shanghai
        gh1 = encoder.encode(39.9847, 116.3184)
        gh2 = encoder.encode(31.2304, 121.4737)
        
        # Should be completely different at high precision
        assert gh1 != gh2


class TestKAnonymity:
    """Tests for k-anonymity calculation."""

    def test_calculate_k_anonymity_high(self):
        """Test k-anonymity with high values."""
        geohashes = ["wx4g0e", "wx4g0e", "wx4g0e", "wx4g0e", "wx4g0e"]
        result = calculate_k_anonymity(geohashes, k=3)
        
        assert result["is_k_anonymous"] is True
        assert result["k"] == 3

    def test_calculate_k_anonymity_low(self):
        """Test k-anonymity with low values."""
        geohashes = ["wx4g0e", "wx4g0e", "wx4g0e", "different_hash"]
        result = calculate_k_anonymity(geohashes, k=5)
        
        assert result["is_k_anonymous"] is False
