"""Unit tests for GPS data loader."""
import pytest
from pathlib import Path
from src.data.loader import GeoLifeLoader


class TestGeoLifeLoader:
    """Tests for GeoLifeLoader."""

    def test_initialization(self, tmp_path):
        """Test loader initialization."""
        loader = GeoLifeLoader(data_dir=str(tmp_path))
        assert loader.data_dir == Path(tmp_path)

    def test_header_lines_constant(self):
        """Test header lines constant."""
        assert GeoLifeLoader.HEADER_LINES == 6
