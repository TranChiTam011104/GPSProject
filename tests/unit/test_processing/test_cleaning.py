"""
Unit tests cho src.processing — kiểm thử từng stage riêng lẻ.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from gps.data.processing import (
    REASON_DUPLICATE,
    REASON_DUPLICATE_AMBIGUOUS,
    REASON_DUPLICATE_INVALID_ANCHORS,
    REASON_DUPLICATE_REJECTED,
    REASON_SPIKE,
    CleaningThresholds,
    _resolve_duplicate_groups,
    clean_altitude,
    clean_trajectory,
    filter_physical_bounds,
    recheck_invalid_anchor_groups,
    remove_speed_spikes,
    resolve_duplicate_timestamps,
    segment_trajectories,
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
def df_clean(sample_df, thresholds):
    """DataFrame sau các bước làm sạch trước khi cắt segment."""
    df = filter_physical_bounds(sample_df, thresholds)
    df, _ = resolve_duplicate_timestamps(df, thresholds)
    return clean_altitude(df, thresholds)


def make_track(rows):
    """rows: list (HH:MM:SS, lat, lon[, altitude_ft]) trong ngày 2024-01-01."""
    return pd.DataFrame({
        "datetime": pd.to_datetime([f"2024-01-01 {r[0]}" for r in rows]),
        "lat": [float(r[1]) for r in rows],
        "lon": [float(r[2]) for r in rows],
        "altitude": [float(r[3]) if len(r) > 3 else 100.0 for r in rows],
    })


# Bắc Kinh / Thượng Hải cách nhau ~1,070 km -> nhảy giữa 2 nơi trong vài giây
# là > 1100 km/h (ngưỡng impossible_speed_kmh, notebooks/01_speed_threshold).
BJ = (39.9847, 116.3184)
SH = (31.2391, 121.4944)


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

class TestResolveDuplicateTimestamps:
    def test_exact_duplicate_keeps_one(self, sample_df, thresholds):
        df = pd.concat([sample_df, sample_df.iloc[[0]]], ignore_index=True)
        kept, quarantined = resolve_duplicate_timestamps(df, thresholds)
        assert len(kept) == 4
        assert kept["datetime"].duplicated().sum() == 0
        assert quarantined.empty

    def test_far_candidate_rejected(self, thresholds):
        df = make_track([
            ("10:00:00", *BJ),
            ("10:00:05", *SH),                      # ứng viên nhảy xa
            ("10:00:05", BJ[0] + 0.0001, BJ[1]),    # ứng viên gần (~11 m)
            ("10:00:10", *BJ),
        ])
        kept, quarantined = resolve_duplicate_timestamps(df, thresholds)
        assert len(kept) == 3
        assert SH[0] not in kept["lat"].values
        # ứng viên bị loại vì tốc độ được giữ lại trong quarantine để soát
        assert quarantined["reason"].tolist() == [REASON_DUPLICATE_REJECTED]
        assert quarantined["lat"].tolist() == [SH[0]]

    def test_ambiguous_group_quarantined(self, thresholds):
        # 2 ứng viên đều hợp lệ (~500 m trong 5 s = 360 km/h) nhưng cách nhau
        # ~1 km > 200 m -> không đủ dữ liệu để chọn -> quarantine cả nhóm
        df = make_track([
            ("10:00:00", *BJ),
            ("10:00:05", BJ[0] + 0.0045, BJ[1]),
            ("10:00:05", BJ[0] - 0.0045, BJ[1]),
            ("10:00:10", *BJ),
        ])
        kept, quarantined, decisions = _resolve_duplicate_groups(df, thresholds)
        assert len(kept) == 2
        assert kept["datetime"].duplicated().sum() == 0
        assert len(quarantined) == 2
        assert (quarantined["reason"] == REASON_DUPLICATE_AMBIGUOUS).all()
        assert decisions["decision"].tolist() == ["ambiguous"]
        assert decisions["valid_spread_m"].iloc[0] == pytest.approx(1000, rel=0.01)

    def test_spread_ignores_rejected_candidates(self, thresholds):
        # Ứng viên ở xa đã bị loại vì tốc độ -> không tính vào độ phân tán;
        # 2 ứng viên hợp lệ còn lại gần nhau -> tie_break bình thường
        df = make_track([
            ("10:00:00", *BJ),
            ("10:00:05", *SH),
            ("10:00:05", BJ[0] + 0.0001, BJ[1]),
            ("10:00:05", BJ[0] + 0.0002, BJ[1]),
            ("10:00:10", *BJ),
        ])
        kept, quarantined, decisions = _resolve_duplicate_groups(df, thresholds)
        assert decisions["decision"].tolist() == ["tie_break"]
        assert len(kept) == 3
        assert quarantined["reason"].tolist() == [REASON_DUPLICATE_REJECTED]

    def test_tie_break_picks_lowest_speed(self, thresholds):
        # Ứng viên đứng trước trong file nhưng xa quỹ đạo hơn (~22 m so với ~11 m)
        # -> giữ ứng viên có max(v_in, v_out) nhỏ nhất, không theo thứ tự file
        df = make_track([
            ("10:00:00", *BJ),
            ("10:00:05", BJ[0] + 0.0002, BJ[1]),
            ("10:00:05", BJ[0] + 0.0001, BJ[1]),
            ("10:00:10", *BJ),
        ])
        kept, quarantined, decisions = _resolve_duplicate_groups(df, thresholds)
        assert decisions["decision"].tolist() == ["tie_break"]
        assert kept.loc[1, "lat"] == BJ[0] + 0.0001
        assert quarantined.empty  # ứng viên hợp lệ không được chọn thì bỏ, không quarantine

    def test_speed_tie_prefers_valid_altitude(self, thresholds):
        # 2 ứng viên đối xứng quanh quỹ đạo -> cùng tốc độ -> altitude hợp lệ trước
        df = make_track([
            ("10:00:00", *BJ),
            ("10:00:05", BJ[0] + 0.0001, BJ[1], -777),   # đứng trước nhưng altitude lỗi
            ("10:00:05", BJ[0] - 0.0001, BJ[1], 150),
            ("10:00:10", *BJ),
        ])
        kept, _, decisions = _resolve_duplicate_groups(df, thresholds)
        row = kept[kept["datetime"] == pd.Timestamp("2024-01-01 10:00:05")]
        assert len(row) == 1
        assert row["altitude"].iloc[0] == 150
        assert decisions["decision"].tolist() == ["tie_break"]

    def test_speed_tie_keeps_first_in_file(self, thresholds):
        df = make_track([
            ("10:00:00", *BJ),
            ("10:00:05", BJ[0] - 0.0001, BJ[1]),
            ("10:00:05", BJ[0] + 0.0001, BJ[1]),
            ("10:00:10", *BJ),
        ])
        kept, _ = resolve_duplicate_timestamps(df, thresholds)
        assert kept.loc[1, "lat"] == BJ[0] - 0.0001

    def test_invalid_anchors_quarantined_with_own_reason(self, thresholds):
        # Chính 2 điểm neo nhảy Bắc Kinh -> Thượng Hải trong 10 s (> 1100 km/h)
        # -> không ứng viên nào hợp lệ được, lý do là điểm neo chứ không phải ứng viên
        df = make_track([
            ("10:00:00", *BJ),
            ("10:00:05", BJ[0] + 0.0001, BJ[1]),
            ("10:00:05", SH[0] + 0.0001, SH[1]),
            ("10:00:10", *SH),
        ])
        kept, quarantined, decisions = _resolve_duplicate_groups(df, thresholds)
        assert decisions["decision"].tolist() == ["invalid_anchors"]
        assert len(kept) == 2
        assert len(quarantined) == 2
        assert (quarantined["reason"] == REASON_DUPLICATE_INVALID_ANCHORS).all()

    def test_no_valid_candidate_quarantines_group(self, thresholds):
        df = make_track([
            ("10:00:00", *BJ),
            ("10:00:05", *SH),
            ("10:00:05", SH[0] + 0.001, SH[1]),
            ("10:00:10", *BJ),
        ])
        kept, quarantined, decisions = _resolve_duplicate_groups(df, thresholds)
        assert len(kept) == 2
        assert kept["datetime"].duplicated().sum() == 0
        assert len(quarantined) == 2
        assert (quarantined["reason"] == REASON_DUPLICATE).all()
        assert decisions["decision"].tolist() == ["no_valid"]

    def test_single_valid_decision(self, thresholds):
        df = make_track([
            ("10:00:00", *BJ),
            ("10:00:05", *SH),
            ("10:00:05", *BJ),
            ("10:00:10", *BJ),
        ])
        _, _, decisions = _resolve_duplicate_groups(df, thresholds)
        assert decisions["decision"].tolist() == ["single_valid"]

    def test_spike_anchor_group_rescued_after_spike_removal(self, thresholds):
        # Điểm neo trước của nhóm 10:00:10 là điểm gai (nhảy sang Thượng Hải rồi về)
        # -> lúc đầu bị quarantine vì điểm neo, sau khi loại gai thì xử lý lại được
        df = make_track([
            ("10:00:00", *BJ),
            ("10:00:05", *SH),                        # điểm gai
            ("10:00:10", BJ[0] + 0.0003, BJ[1]),
            ("10:00:10", BJ[0] + 0.0001, BJ[1]),
            ("10:00:15", *BJ),
            ("10:00:20", *BJ),
        ])
        kept, q_dup = resolve_duplicate_timestamps(df, thresholds)
        assert (q_dup["reason"] == REASON_DUPLICATE_INVALID_ANCHORS).all()
        kept, q_spike = remove_speed_spikes(kept, thresholds)
        kept, q_dup = recheck_invalid_anchor_groups(kept, q_dup, thresholds)
        row = kept[kept["datetime"] == pd.Timestamp("2024-01-01 10:00:10")]
        assert row["lat"].tolist() == [BJ[0] + 0.0001]   # ứng viên khớp chuyển động hơn
        assert q_dup.empty
        assert q_spike["lat"].tolist() == [SH[0]]

    def test_shifted_anchor_group_stays_quarantined(self, thresholds):
        # Quỹ đạo lệch hẳn sang Thượng Hải (không quay lại) -> không có điểm gai,
        # không biết phía nào đúng -> nhóm vẫn bị quarantine vì điểm neo
        df = make_track([
            ("10:00:00", *BJ),
            ("10:00:05", *BJ),
            ("10:00:10", BJ[0] + 0.0001, BJ[1]),
            ("10:00:10", SH[0] + 0.0001, SH[1]),
            ("10:00:15", *SH),
            ("10:00:20", *SH),
        ])
        kept, q_dup = resolve_duplicate_timestamps(df, thresholds)
        kept, _ = remove_speed_spikes(kept, thresholds)
        kept, q_dup = recheck_invalid_anchor_groups(kept, q_dup, thresholds)
        assert pd.Timestamp("2024-01-01 10:00:10") not in set(kept["datetime"])
        assert len(q_dup) == 2
        assert (q_dup["reason"] == REASON_DUPLICATE_INVALID_ANCHORS).all()

    def test_candidate_at_first_timestamp(self, thresholds):
        # Không có điểm trước -> chỉ xét điểm sau
        df = make_track([
            ("10:00:00", *SH),
            ("10:00:00", *BJ),
            ("10:00:05", *BJ),
        ])
        kept, quarantined = resolve_duplicate_timestamps(df, thresholds)
        assert len(kept) == 2
        assert kept.loc[0, "lat"] == BJ[0]
        assert quarantined["reason"].tolist() == [REASON_DUPLICATE_REJECTED]


class TestRemoveSpeedSpikes:
    def test_single_spike_removed(self, thresholds):
        df = make_track([
            ("10:00:00", *BJ),
            ("10:00:05", *SH),
            ("10:00:10", *BJ),
        ])
        kept, quarantined = remove_speed_spikes(df, thresholds)
        assert len(kept) == 2
        assert SH[0] not in kept["lat"].values
        assert quarantined["reason"].tolist() == [REASON_SPIKE]

    def test_sustained_fast_motion_kept(self, thresholds):
        # 3.5 km mỗi 10 s ~ 1260 km/h, di chuyển liên tục một hướng:
        # v_skip cũng > ngưỡng nên không phải gai.
        step = 3.5 / 111.195
        df = make_track([
            (f"10:00:{10 * i:02d}", BJ[0] + step * i, BJ[1]) for i in range(5)
        ])
        kept, quarantined = remove_speed_spikes(df, thresholds)
        assert len(kept) == 5
        assert quarantined.empty

    def test_alternating_region_removed(self, thresholds):
        # A-B-A-B-A: mọi điểm giữa đều là gai -> chỉ còn 2 đầu mút
        df = make_track([
            ("10:00:00", *BJ),
            ("10:00:05", *SH),
            ("10:00:10", *BJ),
            ("10:00:15", *SH),
            ("10:00:20", *BJ),
        ])
        kept, quarantined = remove_speed_spikes(df, thresholds)
        assert kept["datetime"].dt.strftime("%H:%M:%S").tolist() == ["10:00:00", "10:00:20"]
        assert len(quarantined) == 3

    def test_normal_track_unchanged(self, sample_df, thresholds):
        kept, quarantined = remove_speed_spikes(sample_df, thresholds)
        assert len(kept) == len(sample_df)
        assert quarantined.empty

    def test_fewer_than_three_rows_unchanged(self, thresholds):
        df = make_track([("10:00:00", *BJ), ("10:00:05", *SH)])
        kept, quarantined = remove_speed_spikes(df, thresholds)
        assert len(kept) == 2
        assert quarantined.empty


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


# ── Stage 6: Segmentation ─────────────────────────────────────────────────────

class TestSegmentTrajectories:
    def test_no_gap_no_split(self, df_clean, thresholds):
        df_seg = segment_trajectories(df_clean, thresholds)
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
        df_seg = segment_trajectories(df, thresholds)
        assert df_seg["sub_trip_id"].nunique() == 2

    def test_impossible_jump_splits_but_keeps_points(self, thresholds):
        # Khối lệch 2 điểm (không phải gai 1 điểm) -> không xoá, chỉ ngắt nối
        df = make_track([
            ("10:00:00", *BJ),
            ("10:00:05", *SH),
            ("10:00:10", *SH),
            ("10:00:15", *BJ),
        ])
        df_seg = segment_trajectories(df, thresholds)
        assert len(df_seg) == 4
        assert df_seg["sub_trip_id"].tolist() == [0, 1, 1, 2]

    def test_sustained_fast_motion_splits_every_step(self, thresholds):
        step = 3.5 / 111.195  # ~1260 km/h với bước 10 s
        df = make_track([
            (f"10:00:{10 * i:02d}", BJ[0] + step * i, BJ[1]) for i in range(3)
        ])
        df_seg = segment_trajectories(df, thresholds)
        assert df_seg["sub_trip_id"].nunique() == 3

    def test_sub_trip_id_starts_at_zero(self, df_clean, thresholds):
        df_seg = segment_trajectories(df_clean, thresholds)
        assert df_seg["sub_trip_id"].iloc[0] == 0


# ── Master pipeline ─────────────────────────────────────────────────────────────

def write_plt(path, rows):
    """rows: list (HH:MM:SS, lat, lon[, altitude_ft]) ngày 2024-01-01 -> file .plt GeoLife."""
    header = "Geolife trajectory\nWGS 84\nAltitude is in Feet\nReserved 3\n0,2,255,My Track,0,0,2,8421376\n0\n"
    lines = [
        f"{r[1]},{r[2]},0,{r[3] if len(r) > 3 else 100},45292.0,2024-01-01,{r[0]}"
        for r in rows
    ]
    path.write_text(header + "\n".join(lines) + "\n")
    return path


@pytest.fixture
def plt_path(tmp_path):
    # Trùng timestamp 10:00:05 (1 ứng viên ở Thượng Hải) + 1 điểm gai 10:00:15
    return write_plt(tmp_path / "20240101100000.plt", [
        ("10:00:00", *BJ),
        ("10:00:05", *SH),
        ("10:00:05", BJ[0] + 0.0001, BJ[1]),
        ("10:00:10", *BJ),
        ("10:00:15", *SH),
        ("10:00:20", *BJ),
        ("10:00:25", BJ[0] + 0.0002, BJ[1]),
    ])


class TestCleanTrajectory:
    def test_output(self, plt_path, thresholds):
        df, quarantined = clean_trajectory(plt_path, "999", thresholds)
        assert list(df.columns) == [
            "user_id", "source_file", "datetime", "timestamp_local", "tz_name",
            "lat", "lon", "altitude", "altitude_m", "sub_trip_id",
        ]
        assert len(df) == 5
        assert (df["tz_name"] == "Asia/Shanghai").all()
        assert not df["datetime"].duplicated().any()
        assert SH[0] not in df["lat"].values
        assert (df["sub_trip_id"] == "999_20240101100000_0").all()
        assert sorted(quarantined["reason"]) == sorted([REASON_DUPLICATE_REJECTED, REASON_SPIKE])

    def test_returns_none_on_invalid_path(self, thresholds):
        df, quarantined = clean_trajectory(Path("nonexistent/file.plt"), "999", thresholds)
        assert df is None
        assert quarantined.empty
