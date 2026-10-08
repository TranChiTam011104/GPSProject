"""StayPointInput / coerce_stay_points: the classifier's single input format."""
import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from gps.features.stay_point import StayPointDetector, stay_points_to_frame
from gps.models.base import StayPointInput, coerce_stay_points

ARRIVAL = datetime(2008, 10, 23, 14, 30)


def test_pipeline_rows_are_accepted():
    """Rows of data/processed/staypoints/user_{id}.parquet use arrival/departure column names."""
    times = pd.date_range("2008-10-23 14:30", periods=41, freq="1min")
    track = pd.DataFrame({"datetime": times, "lat": 39.9847, "lon": 116.3184})
    frame = stay_points_to_frame(StayPointDetector().detect(track), "010")
    sp = coerce_stay_points(frame.to_dict("records"))[0]
    assert sp.arrival_time == ARRIVAL
    assert sp.duration_minutes == pytest.approx(40)
    assert sp.observed_minutes == pytest.approx(40)
    assert sp.altitude_m is None                       # NaN in the parquet means "not given"


def test_detector_stay_points_are_accepted():
    times = pd.date_range("2008-10-23 14:30", periods=41, freq="1min")
    stays = StayPointDetector().detect(pd.DataFrame({"datetime": times, "lat": 39.9847, "lon": 116.3184}))
    assert coerce_stay_points(stays)[0].arrival_time == ARRIVAL


def test_tz_aware_times_become_naive_gmt():
    beijing = timezone(timedelta(hours=8))
    sp = StayPointInput.from_dict({"lat": 39.98, "lon": 116.31,
                                   "arrival_time": "2008-10-23T22:30:00+08:00",
                                   "departure_time": datetime(2008, 10, 24, 6, 30, tzinfo=beijing)})
    assert sp.arrival_time == ARRIVAL
    assert sp.arrival_time.tzinfo is None
    assert sp.duration_minutes == pytest.approx(8 * 60)


@pytest.mark.parametrize(("raw", "message"), [
    ({"lat": 39.98, "lon": 116.31, "timestamp": ARRIVAL}, "arrival"),                          # raw GPS point
    ({"lat": 39.98, "lon": 116.31, "arrival_time": ARRIVAL}, "departure"),                     # no departure
    ({"lat": 39.98, "lon": 116.31, "arrival_time": ARRIVAL, "departure_time": ARRIVAL}, "after"),  # zero length
])
def test_invalid_stay_points_are_rejected(raw, message):
    with pytest.raises(ValueError, match=message):
        StayPointInput.from_dict(raw)


def test_missing_optional_fields_are_none():
    sp = StayPointInput.from_dict({"lat": 39.98, "lon": 116.31, "arrival_time": ARRIVAL,
                                   "departure_time": ARRIVAL + timedelta(hours=1), "altitude_m": math.nan})
    assert sp.observed_minutes is None
    assert sp.altitude_m is None
