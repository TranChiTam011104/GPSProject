"""Pytest configuration and shared fixtures."""
import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd


# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def sample_stay_points():
    """Sample stay-points for testing."""
    base_time = datetime(2024, 1, 1, 22, 0, 0)
    
    return [
        {
            "lat": 39.9847,
            "lng": 116.3184,
            "arrival_time": base_time,
            "departure_time": base_time + timedelta(hours=8),
            "duration_minutes": 480
        },
        {
            "lat": 40.1234,
            "lng": 116.5678,
            "arrival_time": base_time + timedelta(hours=9),
            "departure_time": base_time + timedelta(hours=18),
            "duration_minutes": 540
        },
        {
            "lat": 39.9847,
            "lng": 116.3185,
            "arrival_time": base_time + timedelta(days=1),
            "departure_time": base_time + timedelta(days=1, hours=8),
            "duration_minutes": 480
        }
    ]


@pytest.fixture
def sample_trajectory():
    """Sample GPS trajectory for testing."""
    base_time = datetime(2024, 1, 1, 10, 0, 0)
    
    data = {
        "lat": [39.9847, 39.9848, 39.9850, 39.9855, 39.9860],
        "lng": [116.3184, 116.3185, 116.3190, 116.3195, 116.3200],
        "timestamp": [
            base_time + timedelta(minutes=i*5)
            for i in range(5)
        ]
    }
    
    return pd.DataFrame(data)


@pytest.fixture
def mock_user_id():
    """Sample user ID."""
    return "test_user_123"


@pytest.fixture
def model_config():
    """Default model configuration."""
    return {
        "timezone": "Asia/Shanghai",
        "home_hour_start": 22,
        "home_hour_end": 6,
        "office_hour_start": 9,
        "office_hour_end": 18,
        "work_days": [0, 1, 2, 3, 4]
    }
