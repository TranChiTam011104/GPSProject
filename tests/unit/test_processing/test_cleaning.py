"""
Unit tests cho src.processing — kiểm thử từng stage riêng lẻ.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from gps.data.processing import (
    filter_physical_bounds,
    deduplicate_timestamps,
    clean_altitude,
    compute_kinematics,
    filter_speed_drift,
    segment_trajectories,
    load_labels,
    match_labels,
    clean_and_segment_trajectory,
    load_plt_file,
    CleaningThresholds,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def thresholds():
    return CleaningThresholds()


@pytest.fixture
def sample_df():
    """DataFrame thô đơn giản: lat, lon, altitude, datetime."""
    return pd.DataFrame({
        "datetime": pd.to_datetime([
            "2024-01-01 10:00:00",
            "2024-01-01 10:01:00",
            "2024-01-01 10:02:00",
            "2024-01-01 10:03:00",
        ]),
        "lat":  [39.9847, 39.9848, 39.9850, 39.9855],
        "lon":  [116.3184, 116.3185, 116.3190, 116.3195],
        "altitude": [66.0, 67.0, -777.0, 68.0],
    })


@pytest.fixture
def df_with_kinematics(sample_df, thresholds):
    """DataFrame sau stage 4 (kinematics computed)."""
    df = sample_df.copy()
    df = filter_physical_bounds(df, thresholds)
    df = deduplicate_timestamps(df)
    df = clean_altitude(df, thresholds)
    df = compute_kinematics(df)
    return df


# ── Stage 2: Physical bounds ───────────────────────────────────────────────────

class TestFilterPhysicalBounds:
    def test_keep_valid_points(self, sample_df, thresholds):
        df_clean = filter_physical_bounds(sample_df, thresholds)
        assert len(df_clean) == 4

    def test_drop_lat_out_of_range(self, sample_df, thresholds):
        df = sample_df.copy()
        df.loc[0, "lat"] = 400.0
        df_clean = filter_physical_bounds(df, thresholds)
        assert len(df_clean) == 3
        assert 400.0 not in df_clean["lat"].values

    def test_drop_lon_out_of_range(self, sample_df, thresholds):
        df = sample_df.copy()
        df.loc[0, "lon"] = -200.0
        df_clean = filter_physical_bounds(df, thresholds)
        assert len(df_clean) == 3

    def test_drop_zero_zero(self, sample_df, thresholds):
        df = sample_df.copy()
        df.loc[0, "lat"] = 0.0
        df.loc[0, "lon"] = 0.0
        df_clean = filter_physical_bounds(df, thresholds)
        assert len(df_clean) == 3
        assert not ((df_clean["lat"] == 0.0) & (df_clean["lon"] == 0.0)).any()


# ── Stage 3: Deduplication ─────────────────────────────────────────────────────

class TestDeduplicateTimestamps:
    def test_remove_duplicate_timestamps(self, sample_df, thresholds):
        df = sample_df.copy()
        # Thêm dòng trùng timestamp
        dup_row = df.iloc[0].copy()
        df = pd.concat([df, dup_row.to_frame().T], ignore_index=True)
        df_clean = deduplicate_timestamps(df)
        assert len(df_clean) == 4
        assert df_clean["datetime"].duplicated().sum() == 0

    def test_keep_first_occurrence(self, sample_df, thresholds):
        df = sample_df.copy()
        dup_row = df.iloc[0].copy()
        dup_row["lat"] = 999.0  # khác lat
        df = pd.concat([df, dup_row.to_frame().T], ignore_index=True)
        df_clean = deduplicate_timestamps(df)
        # Phải giữ dòng gốc, không phải dòng trùng
        assert 999.0 not in df_clean["lat"].values


# ── Stage 4: Altitude cleaning ─────────────────────────────────────────────────

class TestCleanAltitude:
    def test_replaces_minus777_with_nan(self, sample_df, thresholds):
        df = clean_altitude(sample_df, thresholds)
        # Điểm có altitude=-777 phải được thay bằng interpolated giá trị
        assert df["altitude_m"].notna().all()

    def test_conversion_feet_to_meters(self, sample_df, thresholds):
        df = clean_altitude(sample_df, thresholds)
        # Vì clean_altitude thay -777 → NaN trong altitude, so sánh với copy gốc
        original = sample_df.copy()
        for idx, row in df.iterrows():
            if original.loc[idx, "altitude"] != -777:
                expected = original.loc[idx, "altitude"] * 0.3048
                assert abs(row["altitude_m"] - expected) < 0.001, \
                    f"Sai hệ số chuyển đổi: {row['altitude_m']} vs {expected}"

    def test_interpolation_fills_nan(self, sample_df, thresholds):
        df = clean_altitude(sample_df, thresholds)
        assert df["altitude_m"].notna().all()

    def test_bfill_ffill_edge_cases(self, thresholds):
        # Nếu điểm đầu hoặc cuối bị NaN → fill phải hoạt động
        df = pd.DataFrame({
            "datetime": pd.to_datetime(["2024-01-01 10:00:00", "2024-01-01 10:01:00"]),
            "lat":  [39.9847, 39.9848],
            "lon":  [116.3184, 116.3185],
            "altitude": [50.0, -777.0],
        })
        result = clean_altitude(df, thresholds)
        # Điểm đầu valid, điểm sau được nội suy từ điểm trước
        assert result["altitude_m"].notna().all()
        # Giá trị interpolated = 50 * 0.3048
        assert abs(result["altitude_m"].iloc[1] - 15.24) < 0.1


# ── Stage 5 & 6: Kinematics + Speed filter ────────────────────────────────────

class TestComputeKinematics:
    def test_delta_time_s_computed(self, df_with_kinematics):
        assert "delta_time_s" in df_with_kinematics.columns
        assert df_with_kinematics["delta_time_s"].iloc[0] == 0.0
        assert df_with_kinematics["delta_time_s"].iloc[1] == 60.0

    def test_speed_kmh_computed(self, df_with_kinematics):
        assert "speed_kmh" in df_with_kinematics.columns
        # Điểm đầu tiên NaN, các điểm sau phải có giá trị
        assert df_with_kinematics["speed_kmh"].iloc[1:].notna().all()

    def test_speed_positive_realistic(self, df_with_kinematics, thresholds):
        # Các điểm gần nhau phải có vận tốc hợp lý
        speeds = df_with_kinematics["speed_kmh"].dropna()
        assert (speeds >= 0).all()
        # Dưới ngưỡng 180 km/h
        assert (speeds <= thresholds.max_speed_kmh).all()


class TestFilterSpeedDrift:
    def test_drop_extreme_speed(self, sample_df, thresholds):
        df = sample_df.copy()
        # Điểm nhảy từ 39.98 → 40.5 trong 60s → ~57 km → ~3400 km/h >> 180 km/h
        df.loc[1, "lat"] = 40.5
        df = filter_physical_bounds(df, thresholds)
        df = deduplicate_timestamps(df)
        df = clean_altitude(df, thresholds)
        df = compute_kinematics(df)
        df_clean = filter_speed_drift(df, thresholds)
        # Điểm nhảy phải bị loại
        assert 40.5 not in df_clean["lat"].values

    def test_recomputes_kinematics_after_filter(self, df_with_kinematics, thresholds):
        df_clean = filter_speed_drift(df_with_kinematics, thresholds)
        assert "delta_time_s" in df_clean.columns
        assert "speed_kmh" in df_clean.columns


# ── Stage 7: Segmentation ─────────────────────────────────────────────────────

class TestSegmentTrajectories:
    def test_no_gap_no_split(self, df_with_kinematics, thresholds):
        df_seg = segment_trajectories(df_with_kinematics, thresholds)
        # Mọi điểm trong cùng sub-trip
        assert df_seg["sub_trip_id"].nunique() == 1

    def test_gap_triggers_new_trip(self, sample_df, thresholds):
        df = sample_df.copy()
        # Thêm điểm cách 30 phút → gap > 1200s
        long_gap = pd.DataFrame({
            "datetime": pd.to_datetime(["2024-01-01 10:30:00"]),
            "lat":  [39.9900],
            "lon":  [116.3200],
            "altitude": [70.0],
        })
        df = pd.concat([df, long_gap], ignore_index=True)
        df = filter_physical_bounds(df, thresholds)
        df = deduplicate_timestamps(df)
        df = clean_altitude(df, thresholds)
        df = compute_kinematics(df)
        df = filter_speed_drift(df, thresholds)
        df_seg = segment_trajectories(df, thresholds)
        assert df_seg["sub_trip_id"].nunique() == 2

    def test_sub_trip_id_starts_at_zero(self, df_with_kinematics, thresholds):
        df_seg = segment_trajectories(df_with_kinematics, thresholds)
        assert df_seg["sub_trip_id"].iloc[0] == 0


# ── Stage 8: Label matching ────────────────────────────────────────────────────

class TestMatchLabels:
    def test_unknown_when_no_labels(self, df_with_kinematics):
        df_matched = match_labels(df_with_kinematics, None)
        assert (df_matched["mode"] == "unknown").all()

    def test_unknown_when_no_overlap(self, df_with_kinematics):
        labels_df = pd.DataFrame({
            "start_datetime": pd.to_datetime(["2025-01-01 10:00:00"]),
            "end_datetime":   pd.to_datetime(["2025-01-01 11:00:00"]),
            "mode": ["bus"],
        })
        df_matched = match_labels(df_with_kinematics, labels_df)
        assert (df_matched["mode"] == "unknown").all()

    def test_match_overlapping_interval(self, sample_df, thresholds):
        labels_df = pd.DataFrame({
            "start_datetime": pd.to_datetime(["2024-01-01 10:00:00"]),
            "end_datetime":   pd.to_datetime(["2024-01-01 10:02:00"]),
            "mode": ["train"],
        })
        df = sample_df.copy()
        df = filter_physical_bounds(df, thresholds)
        df = deduplicate_timestamps(df)
        df = clean_altitude(df, thresholds)
        df = compute_kinematics(df)
        df = filter_speed_drift(df, thresholds)
        df = segment_trajectories(df, thresholds)
        df_matched = match_labels(df, labels_df)
        assert (df_matched["mode"] == "train").any()


# ── Master pipeline ─────────────────────────────────────────────────────────────

class TestCleanAndSegmentTrajectory:
    def test_returns_dataframe_on_valid_file(self):
        sample_path = Path("data/Geolife Trajectories 1.3/Data/010/Trajectory/20071231170243.plt")
        if not sample_path.exists():
            pytest.skip("Sample file not found")
        df = clean_and_segment_trajectory(sample_path, "010", None)
        assert df is not None
        assert not df.empty
        assert len(df.columns) == 11
        assert "user_id" in df.columns
        assert "sub_trip_id" in df.columns
        assert "mode" in df.columns

    def test_returns_none_on_invalid_path(self):
        df = clean_and_segment_trajectory(
            Path("nonexistent/file.plt"), "999", None
        )
        assert df is None

    def test_keeps_first_of_duplicates(self):
        sample_path = Path("data/Geolife Trajectories 1.3/Data/010/Trajectory/20071231170243.plt")
        if not sample_path.exists():
            pytest.skip("Sample file not found")
        df = clean_and_segment_trajectory(sample_path, "010", None)
        assert df["datetime"].duplicated().sum() == 0
