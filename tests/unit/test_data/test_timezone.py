"""Unit tests for location-based local time (GMT -> timezone of the coordinates)."""
import pandas as pd

from gps.data.timezone import localize_by_location, timezone_names

BEIJING = (39.9847, 116.3184)
SEATTLE = (47.6062, -122.3321)
PHNOM_PENH = (11.5564, 104.9282)


def _df(points, times):
    return pd.DataFrame({"datetime": pd.to_datetime(times),
                         "lat": [p[0] for p in points], "lon": [p[1] for p in points]})


class TestTimezoneNames:
    def test_known_cities(self):
        names = timezone_names([BEIJING[0], SEATTLE[0]], [BEIJING[1], SEATTLE[1]])
        assert names.tolist() == ["Asia/Shanghai", "America/Los_Angeles"]


class TestLocalizeByLocation:
    def test_beijing_is_utc_plus_8_across_midnight(self):
        out = localize_by_location(_df([BEIJING, BEIJING], ["2008-10-23 02:53:04", "2008-10-23 16:30:00"]))
        assert out["tz_name"].tolist() == ["Asia/Shanghai"] * 2
        assert out["timestamp_local"].tolist() == [pd.Timestamp("2008-10-23 10:53:04"),
                                                   pd.Timestamp("2008-10-24 00:30:00")]

    def test_each_point_uses_its_own_timezone(self):
        out = localize_by_location(_df([BEIJING, PHNOM_PENH], ["2008-10-23 02:00:00", "2008-10-23 02:00:00"]))
        assert out["timestamp_local"].tolist() == [pd.Timestamp("2008-10-23 10:00:00"),   # UTC+8
                                                   pd.Timestamp("2008-10-23 09:00:00")]   # UTC+7

    def test_daylight_saving_time(self):
        # Seattle: UTC-7 in summer (PDT), UTC-8 in winter (PST)
        out = localize_by_location(_df([SEATTLE, SEATTLE], ["2008-07-01 20:00:00", "2008-12-01 20:00:00"]))
        assert out["timestamp_local"].tolist() == [pd.Timestamp("2008-07-01 13:00:00"),
                                                   pd.Timestamp("2008-12-01 12:00:00")]

    def test_keeps_original_column_and_input(self):
        df = _df([BEIJING], ["2008-10-23 02:53:04"])
        out = localize_by_location(df)
        pd.testing.assert_series_equal(out["datetime"], df["datetime"])
        assert "timestamp_local" not in df.columns

    def test_missing_column_returns_input(self):
        df = _df([BEIJING], ["2008-10-23 02:53:04"])
        assert localize_by_location(df, column="nope") is df


def test_local_times_per_location():
    from datetime import datetime

    from gps.data.timezone import local_times
    gmt = [datetime(2008, 7, 2, 6, 0), datetime(2008, 7, 2, 6, 0)]
    beijing, seattle = local_times(gmt, [39.98, 47.61], [116.31, -122.33])
    assert beijing == datetime(2008, 7, 2, 14, 0)
    assert seattle == datetime(2008, 7, 1, 23, 0)
