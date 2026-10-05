"""
Integration tests trên dữ liệu GeoLife thật: cleaning pipeline -> stay-point
(mọi điểm của user, cắt tại khoảng ngắt > 18 h) -> heuristic classifier. Tự skip khi máy không có dữ liệu thô.

Thay cho các script khám phá cũ (test_check_output, test_debug_staypoint,
test_heuristic_classifier, test_staypoint_on_processed, test_thresholds).
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gps.data.processing import clean_trajectory
from gps.features.stay_point import DistanceMode, StayPointDetector
from gps.models.base import ClassificationResult
from gps.models.heuristic import HeuristicClassifier

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR_CANDIDATES = [
    PROJECT_ROOT / "data" / "Geolife Trajectories 1.3" / "Data",
    PROJECT_ROOT / "data" / "raw",
]
RAW_DIR = next((d for d in RAW_DIR_CANDIDATES if d.exists()), None)

USER = "010"
N_FILES = 20              # giới hạn số file/user để test chạy nhanh

pytestmark = pytest.mark.skipif(RAW_DIR is None, reason="Không có dữ liệu GeoLife thô")


def _plt_files(user_id: str) -> list[Path]:
    files = sorted((RAW_DIR / user_id / "Trajectory").glob("*.plt"))[:N_FILES]
    if not files:
        pytest.skip(f"Không có file .plt của user {user_id}")
    return files


@pytest.fixture(scope="module")
def clean_frames() -> list[pd.DataFrame]:
    frames = [clean_trajectory(f, USER)[0] for f in _plt_files(USER)]
    return [df for df in frames if df is not None]


@pytest.fixture(scope="module")
def stay_points(clean_frames):
    detector = StayPointDetector(30, 200, DistanceMode.CENTROID)
    # Mọi điểm của user; detect() tự cắt tại khoảng ngắt > 18 h (notebook 04), không gate theo sub_trip_id
    df = pd.concat(clean_frames, ignore_index=True)
    return [(df, detector.detect(df))]


class TestCleanOutput:
    def test_schema(self, clean_frames):
        expected = [
            "user_id", "source_file", "datetime", "timestamp_local", "tz_name",
            "lat", "lon", "altitude", "altitude_m", "sub_trip_id",
        ]
        for df in clean_frames:
            assert list(df.columns) == expected

    def test_no_duplicate_timestamps_within_file(self, clean_frames):
        for df in clean_frames:
            assert not df["datetime"].duplicated().any()

    def test_timestamp_local_follows_location(self, clean_frames):
        # User 010 ghi ở Bắc Kinh -> Asia/Shanghai, giờ địa phương = GMT + 8 h
        df = clean_frames[0]
        assert (df["tz_name"] == "Asia/Shanghai").all()
        assert (df["timestamp_local"] - df["datetime"] == pd.Timedelta(hours=8)).all()

    def test_sub_trip_id_prefixed_by_user_and_file(self, clean_frames):
        for df in clean_frames:
            stem = Path(df["source_file"].iloc[0]).stem
            assert df["sub_trip_id"].str.startswith(f"{USER}_{stem}_").all()


class TestStayPointAndClassifier:
    def test_stay_points_within_recorded_span(self, stay_points):
        for df, sps in stay_points:
            t_min, t_max = df["datetime"].min(), df["datetime"].max()
            for sp in sps:
                assert t_min <= pd.Timestamp(sp.arrival_time) <= pd.Timestamp(sp.departure_time) <= t_max
                assert sp.duration_minutes >= 30

    def test_classifier_runs_on_detected_stay_points(self, stay_points):
        all_sps = [sp for _, sps in stay_points for sp in sps]
        if not all_sps:
            pytest.skip("Không có stay-point nào trong các file đã chọn")
        result = HeuristicClassifier().predict(all_sps)
        assert isinstance(result, ClassificationResult)
        assert result.home is not None or result.office is not None or result.pois
        for loc in [result.home, result.office, *result.pois]:
            if loc is not None:
                assert np.isfinite(loc.lat)
                assert np.isfinite(loc.lon)
