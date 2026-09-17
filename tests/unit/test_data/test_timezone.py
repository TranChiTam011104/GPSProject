"""Unit tests for timezone converter."""
import pytest
from datetime import datetime
from src.data.timezone import TimezoneConverter


class TestTimezoneConverter:
    """Tests for TimezoneConverter."""

    def test_initialization(self):
        """Test converter initialization."""
        converter = TimezoneConverter()
        assert converter.target_timezone == "Asia/Shanghai"

    def test_initialization_custom(self):
        """Test with custom timezone."""
        converter = TimezoneConverter(target_timezone="UTC")
        assert converter.target_timezone == "UTC"
