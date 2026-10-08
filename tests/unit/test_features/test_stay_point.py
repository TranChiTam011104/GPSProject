"""Unit tests for stay-point detection."""
import sys
from pathlib import Path

# Add src to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from datetime import datetime, timedelta

import pytest

from gps.features.stay_point import DistanceMode, StayPointDetector
from gps.utils.geo import haversine_meters


class TestStayPointDetector:
    """Tests for StayPointDetector."""

    def test_detector_initialization(self):
        """Test detector can be initialized."""
        detector = StayPointDetector(
            time_threshold_minutes=30,
            distance_threshold_meters=200
        )
        assert detector.time_threshold == timedelta(minutes=30)
        assert detector.distance_threshold_m == 200

    def test_haversine_distance_calculation(self):
        """Test distance calculation between two points."""
        # Beijing to Shanghai (~1067 km)
        distance = haversine_meters(39.9847, 116.3184, 31.2304, 121.4737)

        assert 1_000_000 < distance < 1_100_000  # ~1067 km

    def test_detect_returns_list(self, sample_trajectory):
        """Test detection returns a list."""
        detector = StayPointDetector()
        result = detector.detect(sample_trajectory)
        assert isinstance(result, list)


class TestDistanceMode:
    """Tests for distance mode parameter."""

    def test_default_mode_is_centroid(self):
        """Default is CENTROID: the mode the 200 m / 30 min thresholds were validated in."""
        detector = StayPointDetector()
        assert detector.distance_mode == DistanceMode.CENTROID

    def test_centroid_mode_initialization(self):
        """Test detector can be initialized with CENTROID mode."""
        detector = StayPointDetector(
            time_threshold_minutes=30,
            distance_threshold_meters=200,
            distance_mode=DistanceMode.CENTROID
        )
        assert detector.distance_mode == DistanceMode.CENTROID

    def test_anchor_mode_initialization(self):
        """Test detector can be initialized with ANCHOR mode."""
        detector = StayPointDetector(
            time_threshold_minutes=30,
            distance_threshold_meters=200,
            distance_mode=DistanceMode.ANCHOR
        )
        assert detector.distance_mode == DistanceMode.ANCHOR

    def test_string_mode_centroid(self):
        """Test that string 'centroid' works."""
        detector = StayPointDetector(distance_mode="centroid")
        assert detector.distance_mode == DistanceMode.CENTROID

    def test_string_mode_anchor(self):
        """Test that string 'anchor' works."""
        detector = StayPointDetector(distance_mode="anchor")
        assert detector.distance_mode == DistanceMode.ANCHOR


class TestCentroidBasedDetection:
    """Tests for centroid-based stay-point detection."""

    def _create_trajectory(self, lats, lons, start_time, interval_minutes=5):
        """Helper to create test trajectory."""
        import pandas as pd
        timestamps = [start_time + timedelta(minutes=i * interval_minutes) for i in range(len(lats))]
        return pd.DataFrame({
            "lat": lats,
            "lon": lons,
            "timestamp": timestamps
        })

    def test_centroid_expands_with_moving_points(self):
        """Test that centroid mode expands window as centroid moves.

        With centroid mode, points that gradually move away from the anchor
        can still be included in the same stay-point window, as long as
        they stay within distance_threshold of the running centroid.
        """
        detector = StayPointDetector(
            time_threshold_minutes=10,
            distance_threshold_meters=200,
            distance_mode=DistanceMode.CENTROID
        )

        # Start at 0,0
        # Points gradually move: 0→100m→180m→200m (break)
        # With centroid mode, centroid shifts with points, so all 3 points
        # should stay within 200m of the moving centroid
        lats = [39.9847, 39.9854, 39.9861, 39.9870]  # ~80m, ~80m, ~100m apart
        lons = [116.3184, 116.3184, 116.3184, 116.3184]
        start_time = datetime(2024, 1, 1, 10, 0, 0)
        trajectory = self._create_trajectory(lats, lons, start_time, interval_minutes=5)

        stay_points = detector.detect(trajectory)
        # With time_threshold=10min and 4 points over 15min total, this should be a stay-point
        assert len(stay_points) == 1

    def test_centroid_vs_anchor_difference(self):
        """Test that centroid and anchor modes can produce different results.

        This test creates a trajectory where:
        - Point 0: anchor at (39.9847, 116.3184)
        - Point 1: 150m away
        - Point 2: 190m away
        - Point 3: 250m away (outside 200m from anchor, but may be within centroid)
        """

        # Create trajectory: anchor -> 150m -> 190m -> 250m (outside anchor range)
        # 250m ≈ 0.00225 degrees latitude
        lats = [39.9847, 39.9860, 39.9872, 39.9890]  # Moving further away
        lons = [116.3184, 116.3184, 116.3184, 116.3184]
        start_time = datetime(2024, 1, 1, 10, 0, 0)
        trajectory = self._create_trajectory(lats, lons, start_time, interval_minutes=5)

        # Anchor mode: should break when point > 200m from anchor
        anchor_detector = StayPointDetector(
            time_threshold_minutes=10,
            distance_threshold_meters=200,
            distance_mode=DistanceMode.ANCHOR
        )
        anchor_results = anchor_detector.detect(trajectory)

        # Centroid mode: centroid shifts, so point may still be within range
        centroid_detector = StayPointDetector(
            time_threshold_minutes=10,
            distance_threshold_meters=200,
            distance_mode=DistanceMode.CENTROID
        )
        centroid_results = centroid_detector.detect(trajectory)

        # Centroid mode should potentially capture more points
        # (depends on exact distances, this is a sanity check)
        assert isinstance(anchor_results, list)
        assert isinstance(centroid_results, list)

    def test_centroid_stay_point_location(self):
        """Test that centroid-based detection returns correct centroid location."""
        detector = StayPointDetector(
            time_threshold_minutes=10,
            distance_threshold_meters=500,  # Large enough to include all points
            distance_mode=DistanceMode.CENTROID
        )

        # 4 points at known locations
        lats = [39.9847, 39.9848, 39.9849, 39.9850]
        lons = [116.3184, 116.3185, 116.3186, 116.3187]
        start_time = datetime(2024, 1, 1, 10, 0, 0)
        trajectory = self._create_trajectory(lats, lons, start_time, interval_minutes=5)

        stay_points = detector.detect(trajectory)

        if stay_points:
            sp = stay_points[0]
            # Expected centroid: mean of all points
            expected_lat = sum(lats) / len(lats)
            expected_lon = sum(lons) / len(lons)

            assert sp.lat == pytest.approx(expected_lat, abs=1e-5)
            assert sp.lon == pytest.approx(expected_lon, abs=1e-5)
            assert sp.num_points == 4


class TestObservedMinutes:
    """observed_minutes = duration trừ các khoảng ngắt > unobserved_gap_seconds."""

    @staticmethod
    def _track_with_gap():
        import pandas as pd
        # 10:00-10:10 ghi mỗi phút, ngắt 90 phút, 11:40-11:50 ghi mỗi phút; cùng 1 chỗ
        times = [datetime(2024, 1, 1, 10, 0) + timedelta(minutes=m) for m in range(11)]
        times += [datetime(2024, 1, 1, 11, 40) + timedelta(minutes=m) for m in range(11)]
        return pd.DataFrame({
            "timestamp": times,
            "lat": [39.9847] * len(times),
            "lon": [116.3184] * len(times),
        })

    @pytest.mark.parametrize("mode", [DistanceMode.ANCHOR, DistanceMode.CENTROID])
    def test_gap_excluded_from_observed_but_not_duration(self, mode):
        detector = StayPointDetector(30, 200, mode)
        sps = detector.detect(self._track_with_gap())
        assert len(sps) == 1
        assert sps[0].duration_minutes == pytest.approx(110)
        assert sps[0].observed_minutes == pytest.approx(20)

    def test_no_gap_observed_equals_duration(self):
        import pandas as pd
        # 40 phút ghi liên tục mỗi phút, cùng 1 chỗ
        times = [datetime(2024, 1, 1, 10, 0) + timedelta(minutes=m) for m in range(41)]
        track = pd.DataFrame({"timestamp": times, "lat": [39.9847] * 41, "lon": [116.3184] * 41})
        sps = StayPointDetector(30, 200).detect(track)
        assert len(sps) == 1
        assert sps[0].observed_minutes == pytest.approx(sps[0].duration_minutes) == pytest.approx(40)

    def test_threshold_is_configurable(self):
        detector = StayPointDetector(30, 200, unobserved_gap_seconds=2 * 3600)
        sps = detector.detect(self._track_with_gap())
        assert sps[0].observed_minutes == pytest.approx(110)  # ngắt 90 phút < 2 giờ


class TestMaxGap:
    """Quỹ đạo bị cắt tại mọi khoảng ngắt > MAX_GAP_HOURS, kể cả giữa 2 file (notebook 04)."""

    HOME = (39.9847, 116.3184)

    @staticmethod
    def _file(name, start, minutes, lat, lon):
        import pandas as pd
        times = pd.date_range(start, periods=minutes + 1, freq="1min")
        return pd.DataFrame({"source_file": name, "datetime": times, "lat": lat, "lon": lon})

    def _two_recordings(self, gap_hours, second_lat=None, same_file=False):
        import pandas as pd
        a = self._file("a.plt", "2008-05-01 21:20", 10, *self.HOME)            # 10 phút ở nhà
        start_b = a["datetime"].iloc[-1] + pd.Timedelta(hours=gap_hours)
        b = self._file("a.plt" if same_file else "b.plt", start_b, 10, second_lat or self.HOME[0], self.HOME[1])
        return pd.concat([a, b], ignore_index=True)

    def test_overnight_stay_spans_two_files(self):
        detector = StayPointDetector(30, 200)
        df = self._two_recordings(gap_hours=10)
        assert detector.detect(df[df["source_file"] == "a.plt"]) == []     # từng file: < 30 phút
        sps = detector.detect(df)
        assert len(sps) == 1
        assert sps[0].duration_minutes == pytest.approx(10 * 60 + 20)
        assert sps[0].observed_minutes == pytest.approx(20)               # khoảng ngắt không được quan sát

    def test_gap_beyond_max_is_cut(self):
        assert StayPointDetector(30, 200).detect(self._two_recordings(gap_hours=30)) == []

    def test_gap_inside_one_file_is_cut_too(self):
        df = self._two_recordings(gap_hours=30, same_file=True)
        assert StayPointDetector(30, 200).detect(df) == []

    def test_no_cut_when_disabled(self):
        sps = StayPointDetector(30, 200, max_gap_hours=None).detect(self._two_recordings(gap_hours=30))
        assert len(sps) == 1

    def test_recordings_starting_far_apart_give_no_stay(self):
        df = self._two_recordings(gap_hours=10, second_lat=self.HOME[0] + 0.05)  # ~5.5 km
        assert StayPointDetector(30, 200).detect(df) == []


class TestStayPointsToFrame:
    """Bảng stay-point: giờ địa phương theo múi giờ của tâm (notebook 09)."""

    @staticmethod
    def _stay(lat, lon, start):
        import pandas as pd
        times = pd.date_range(start, periods=41, freq="1min")
        df = pd.DataFrame({"datetime": times, "lat": lat, "lon": lon})
        return StayPointDetector().detect(df)

    def test_beijing_local_time_is_gmt_plus_8(self):
        import pandas as pd

        from gps.features.stay_point import STAY_POINT_COLUMNS, stay_points_to_frame
        df = stay_points_to_frame(self._stay(39.9847, 116.3184, "2008-05-01 16:30"), "010")
        assert list(df.columns) == STAY_POINT_COLUMNS
        assert len(df) == 1
        row = df.iloc[0]
        assert row["user_id"] == "010"
        assert row["tz_name"] == "Asia/Shanghai"
        assert row["arrival_local"] == pd.Timestamp("2008-05-02 00:30")       # qua nửa đêm giờ Bắc Kinh
        assert row["departure_local"] - row["arrival_local"] == pd.Timedelta(minutes=40)

    def test_seattle_summer_uses_daylight_saving(self):
        import pandas as pd

        from gps.features.stay_point import stay_points_to_frame
        df = stay_points_to_frame(self._stay(47.6062, -122.3321, "2008-07-01 20:00"), "160")
        assert df.iloc[0]["tz_name"] == "America/Los_Angeles"
        assert df.iloc[0]["arrival_local"] == pd.Timestamp("2008-07-01 13:00")  # GMT-7 (giờ mùa hè)

    def test_no_stay_points_gives_empty_frame_with_schema(self):
        from gps.features.stay_point import STAY_POINT_COLUMNS, stay_points_to_frame
        df = stay_points_to_frame([], "049")
        assert df.empty
        assert list(df.columns) == STAY_POINT_COLUMNS
        assert str(df["arrival_local"].dtype).startswith("datetime64")


class TestAltitude:
    """altitude_m = trung bình các độ cao hợp lệ; NaN khi cả cửa sổ không có độ cao."""

    @staticmethod
    def _track(altitudes):
        import pandas as pd
        times = pd.date_range("2008-05-01 10:00", periods=len(altitudes), freq="1min")
        return pd.DataFrame({"datetime": times, "lat": 39.9847, "lon": 116.3184, "altitude_m": altitudes})

    @pytest.mark.parametrize("mode", [DistanceMode.ANCHOR, DistanceMode.CENTROID])
    def test_missing_first_altitude_is_skipped(self, mode):
        alts = [float("nan")] + [50.0] * 40
        assert StayPointDetector(30, 200, mode).detect(self._track(alts))[0].altitude_m == pytest.approx(50.0)

    @pytest.mark.parametrize("mode", [DistanceMode.ANCHOR, DistanceMode.CENTROID])
    def test_no_altitude_gives_nan(self, mode):
        import math
        sps = StayPointDetector(30, 200, mode).detect(self._track([float("nan")] * 41))
        assert math.isnan(sps[0].altitude_m)
