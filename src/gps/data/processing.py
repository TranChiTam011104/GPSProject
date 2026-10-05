"""
GeoLife GPS Data Processing Pipeline.
=====================================
Căn cứ cho từng quyết định: notebooks/README.md (bản prototype ban đầu:
notebooks/archive/02_cleaning_geolife.ipynb).

Một pipeline làm sạch DUY NHẤT; dữ liệu sạch là đầu vào của stay-point
detection và classifier. Mọi ngưỡng đều có căn cứ trong notebook (ghi cạnh
từng ngưỡng ở CleaningThresholds).

Chống tràn RAM & quá nhiệt CPU: xử lý tuần tự theo từng User (ProcessPoolExecutor
nội bộ user -> ghi parquet -> gc.collect() -> sang user tiếp theo),
n_workers = min(4, os.cpu_count()).

Các bước (cho từng file .plt):
  1. Load .plt
  2. Filter physical bounds   - lat in [-90,90], lon in [-180,180], ~(0,0)
  3. Resolve duplicate timestamps - trùng cả toạ độ: giữ 1; khác toạ độ: giữ
                                ứng viên hợp lý về tốc độ với điểm trước/sau;
                                không có ứng viên hợp lý, hoặc các ứng viên hợp
                                lý cách nhau > 200 m -> quarantine cả nhóm
  4. Remove speed spikes      - bỏ điểm nhảy ra rồi quay lại (> 1100 km/h)
  5. Clean altitude           - -777 -> NaN -> feet*0.3048 -> mét -> linear interpolate
  6. Segment trajectories     - sub_trip_id mới khi dt > 1200 s (20 phút)
                                hoặc bước nhảy > 1100 km/h (giữ điểm, ngắt nối)
  7. Localize timezone        - GMT -> giờ địa phương theo toạ độ (cột tz_name, timestamp_local)

Output: Partitioned Apache Parquet -> data/processed/users/user_{user_id}.parquet
        Điểm bị loại ở bước 3-4 -> data/processed/quarantine/user_{user_id}.csv
"""

from __future__ import annotations

import argparse
import gc
import logging
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("processing")


@dataclass
class CleaningThresholds:
    """Ngưỡng của pipeline làm sạch - căn cứ ghi cạnh từng ngưỡng."""

    # 1. Physical bounds (định nghĩa toạ độ hợp lệ)
    lat_min: float = -90.0
    lat_max: float = 90.0
    lon_min: float = -180.0
    lon_max: float = 180.0

    # 2. Altitude sentinel (theo đặc tả GeoLife)
    altitude_invalid: int = -777
    altitude_to_meters: float = 0.3048  # feet -> mét

    # 3. Cắt segment khi khoảng ngắt > 20 phút. Căn cứ: nằm giữa P99.9 và
    #    P99.99 của khoảng ngắt bên trong 1 chuyến đi
    #    (P99.9 = 252 s, P99.99 = 2,170 s; notebooks/03_segment_gap_threshold.ipynb).
    max_gap_seconds: float = 1200.0

    # 4. Minimum points per file to keep (cần >= 2 điểm để có quỹ đạo)
    min_points: int = 2

    # 5. Tốc độ "vật lý bất khả thi" - dùng để giải quyết trùng timestamp và
    #    loại điểm gai. Căn cứ: notebooks/01_speed_threshold.ipynb -
    #    tốc độ thật cao nhất 1,048 km/h (máy bay), lỗi thấp nhất 1,122.7 km/h
    #    (GPS nhảy điểm).
    impossible_speed_kmh: float = 1100.0

    # 6. Nhóm trùng timestamp còn >= 2 ứng viên hợp lệ nhưng cách nhau quá bán
    #    kính stay-point (200 m) -> chọn ứng viên nào sẽ làm đổi
    #    stay-point mà dữ liệu không đủ để chọn: 2 quy tắc chọn hợp lý bất đồng
    #    ở 27/52 nhóm (notebooks/02_duplicate_timestamps.ipynb) -> quarantine.
    ambiguous_duplicate_spread_m: float = 200.0


DEFAULT_THRESHOLDS = CleaningThresholds()


# Column constants
COL_LAT = "lat"
COL_LON = "lon"
COL_DATETIME = "datetime"
COL_ALTITUDE_RAW = "altitude"       # feet, gốc từ .plt
COL_ALTITUDE_M = "altitude_m"      # mét, đã xử lý
COL_TIMESTAMP_LOCAL = "timestamp_local"
COL_TZ_NAME = "tz_name"
COL_SUB_TRIP_ID = "sub_trip_id"
COL_USER_ID = "user_id"
COL_SOURCE_FILE = "source_file"
COL_REASON = "reason"

QUARANTINE_COLS = [
    COL_USER_ID, COL_SOURCE_FILE, COL_DATETIME, COL_LAT, COL_LON, COL_ALTITUDE_RAW, COL_REASON,
]
REASON_DUPLICATE = "duplicate_no_valid_candidate"
REASON_DUPLICATE_INVALID_ANCHORS = "duplicate_invalid_anchors"
REASON_DUPLICATE_AMBIGUOUS = "duplicate_ambiguous_candidates"
REASON_DUPLICATE_REJECTED = "duplicate_rejected_candidate"
REASON_SPIKE = "speed_spike"


# Stage 1 - Load raw .plt file
def load_plt_file(filepath: Path | str) -> pd.DataFrame | None:
    """
    Đọc một file .plt GeoLife thô thành DataFrame.

    Định dạng GeoLife .plt (6 header lines):
      Line 1-6  : metadata (bỏ qua)
      Line 7+   : lat, lon, reserved, altitude, date_days, date_str, time_str

    Returns:
        DataFrame với columns: datetime, lat, lon, altitude (feet),
        or ``None`` if the file does not exist.
    """
    columns = [
        COL_LAT, COL_LON, "reserved", COL_ALTITUDE_RAW,
        "date_days", "date_str", "time_str",
    ]
    try:
        df = pd.read_csv(
            filepath,
            skiprows=6,
            header=None,
            names=columns,
        )
    except FileNotFoundError:
        return None

    df[COL_DATETIME] = pd.to_datetime(
        df["date_str"] + " " + df["time_str"],
        format="%Y-%m-%d %H:%M:%S",
        errors="coerce",
    )
    df = df.dropna(subset=[COL_DATETIME])

    return df[[COL_DATETIME, COL_LAT, COL_LON, COL_ALTITUDE_RAW]].copy()


# Stage 2 - Physical bounds filter
def filter_physical_bounds(
    df: pd.DataFrame,
    thresholds: CleaningThresholds = DEFAULT_THRESHOLDS,
) -> pd.DataFrame:
    """
    Loại bỏ các điểm nằm ngoài biên độ vật lý Trái Đất hoặc điểm rác (0, 0).

    Ngưỡng đã kiểm chứng:
      -90 <= lat <= 90
      -180 <= lon <= 180
      ~(lat == 0 AND lon == 0)
    """
    t = thresholds
    return df[
        df[COL_LAT].between(t.lat_min, t.lat_max, inclusive="both")
        & df[COL_LON].between(t.lon_min, t.lon_max, inclusive="both")
        & ~((df[COL_LAT] == 0.0) & (df[COL_LON] == 0.0))
    ].copy()


# Stage 3 - Resolve duplicate timestamps
def _speed_kmh(
    lat1: np.ndarray, lon1: np.ndarray, t1: np.ndarray,
    lat2: np.ndarray, lon2: np.ndarray, t2: np.ndarray,
) -> np.ndarray:
    """Tốc độ (km/h) giữa từng cặp điểm; t1/t2 là mảng datetime64."""
    dist_m = _haversine_vectorized(lat1, lon1, lat2, lon2)
    dt_s = (t2 - t1) / np.timedelta64(1, "s")
    return dist_m / dt_s * 3.6


def _as_quarantine(rows: pd.DataFrame, reason: str) -> pd.DataFrame:
    """Chuẩn hoá các dòng bị loại về schema QUARANTINE_COLS."""
    return rows.assign(**{COL_REASON: reason}).reindex(columns=QUARANTINE_COLS)


def _valid_spread_m(cands: pd.DataFrame) -> pd.Series:
    """Khoảng cách lớn nhất (m) giữa 2 ứng viên HỢP LỆ bất kỳ trong mỗi nhóm,
    index = mốc thời gian của nhóm. Nhóm < 2 ứng viên hợp lệ không có mặt."""
    v = cands.loc[cands["valid"], ["row", COL_DATETIME, COL_LAT, COL_LON]]
    pairs = v.merge(v, on=COL_DATETIME, suffixes=("_a", "_b"))
    pairs = pairs[pairs["row_a"] < pairs["row_b"]]
    dist = _haversine_vectorized(
        pairs[f"{COL_LAT}_a"].to_numpy(), pairs[f"{COL_LON}_a"].to_numpy(),
        pairs[f"{COL_LAT}_b"].to_numpy(), pairs[f"{COL_LON}_b"].to_numpy(),
    )
    return pd.Series(dist, index=pairs[COL_DATETIME].to_numpy()).groupby(level=0).max()


def _resolve_duplicate_groups(
    df: pd.DataFrame,
    thresholds: CleaningThresholds = DEFAULT_THRESHOLDS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Giải quyết các nhóm bản ghi trùng mốc thời gian. Kiểm chứng:
    notebooks/02_duplicate_timestamps.ipynb (trùng chỉ xảy ra trong 1 file nên xử
    lý theo từng file là đủ).

    - Trùng cả thời gian lẫn toạ độ: giữ 1 bản.
    - Khác toạ độ: mỗi ứng viên được so với "điểm neo" - điểm KHÔNG trùng gần
      nhất trước và sau nó. Ứng viên hợp lệ khi tốc độ tới cả 2 điểm neo đều
      <= impossible_speed_kmh (thiếu 1 phía thì phía đó không tính là bằng
      chứng chống lại). Quyết định mỗi nhóm:
        + "invalid_anchors": chính 2 điểm neo cách nhau > impossible_speed_kmh
                           -> không ứng viên nào hợp lệ được (bất đẳng thức tam
                           giác), quarantine cả nhóm với lý do riêng
        + "no_valid"     : 0 ứng viên hợp lệ -> quarantine cả nhóm
        + "ambiguous"    : >= 2 ứng viên hợp lệ cách nhau > ambiguous_duplicate_spread_m
                           -> quarantine cả nhóm (dữ liệu không đủ để chọn)
        + "single_valid" : đúng 1 ứng viên hợp lệ -> giữ ứng viên đó
        + "tie_break"    : >= 2 ứng viên hợp lệ ở gần nhau -> giữ ứng viên có
                           max(v_in, v_out) nhỏ nhất (khớp chuyển động nhất);
                           hoà thì altitude hợp lệ trước, rồi thứ tự trong file
      Chọn theo tốc độ thay vì theo quy ước để bỏ tính ngẫu nhiên; điểm được chọn
      đổi trung vị < 1 m nên stay-point không đổi. Ngưỡng riêng theo phương tiện
      không dùng vì loại nhầm 1.2–2.3% điểm thật (notebooks/01_speed_threshold.ipynb
      mục 6; notebooks/02_duplicate_timestamps.ipynb phần 3).
      Ở 2 nhánh giữ được ứng viên, các ứng viên bị loại vì tốc độ được đưa vào
      quarantine (REASON_DUPLICATE_REJECTED) để soát lại; ứng viên hợp lệ không
      được chọn (cách ứng viên được giữ <= spread) thì bỏ.

    Returns:
        (kept, quarantined, decisions) - decisions có 1 dòng / nhóm khác toạ độ
        với n_candidates, n_valid, valid_spread_m, decision.
    """
    t = thresholds
    work = df.assign(
        _order=np.arange(len(df)),
        _alt_invalid=(df[COL_ALTITUDE_RAW] == t.altitude_invalid).to_numpy(),
    )
    work = (
        work.sort_values([COL_DATETIME, "_alt_invalid", "_order"], kind="stable")
        .drop_duplicates(subset=[COL_DATETIME, COL_LAT, COL_LON], keep="first")
        .drop(columns=["_order", "_alt_invalid"])
        .reset_index(drop=True)
    )

    is_dup = work.duplicated(subset=[COL_DATETIME], keep=False).to_numpy()
    no_decisions = pd.DataFrame(
        columns=[COL_DATETIME, "n_candidates", "n_valid", "valid_spread_m", "decision"]
    )
    if not is_dup.any():
        return work, _concat_quarantine([]), no_decisions

    ts = work[COL_DATETIME].to_numpy(dtype="datetime64[ns]")
    lat = work[COL_LAT].to_numpy(dtype=float)
    lon = work[COL_LON].to_numpy(dtype=float)

    anchor_idx = np.flatnonzero(~is_dup)
    cand_idx = np.flatnonzero(is_dup)
    # Mốc thời gian của anchor và ứng viên không bao giờ trùng nhau
    # -> pos = số anchor đứng trước ứng viên.
    pos = np.searchsorted(ts[anchor_idx], ts[cand_idx])

    v_in = np.full(len(cand_idx), np.nan)
    v_out = np.full(len(cand_idx), np.nan)
    v_anchors = np.full(len(cand_idx), np.nan)
    has_prev = pos > 0
    has_next = pos < len(anchor_idx)
    if has_prev.any():
        p, c = anchor_idx[pos[has_prev] - 1], cand_idx[has_prev]
        v_in[has_prev] = _speed_kmh(lat[p], lon[p], ts[p], lat[c], lon[c], ts[c])
    if has_next.any():
        c, n = cand_idx[has_next], anchor_idx[pos[has_next]]
        v_out[has_next] = _speed_kmh(lat[c], lon[c], ts[c], lat[n], lon[n], ts[n])
    both = has_prev & has_next
    if both.any():
        p, n = anchor_idx[pos[both] - 1], anchor_idx[pos[both]]
        v_anchors[both] = _speed_kmh(lat[p], lon[p], ts[p], lat[n], lon[n], ts[n])
    valid = ~(v_in > t.impossible_speed_kmh) & ~(v_out > t.impossible_speed_kmh)

    cands = pd.DataFrame({
        "row": cand_idx, COL_DATETIME: ts[cand_idx], "valid": valid,
        COL_LAT: lat[cand_idx], COL_LON: lon[cand_idx],
        # thiếu cả 2 phía -> không có bằng chứng tốc độ -> 0 (chỉ còn thứ tự ưu tiên)
        "score": np.fmax(v_in, v_out),
        "invalid_anchors": v_anchors > t.impossible_speed_kmh,
    })
    cands["score"] = cands["score"].fillna(0.0)
    decisions = cands.groupby(COL_DATETIME, sort=False).agg(
        n_candidates=("row", "size"), n_valid=("valid", "sum"),
        invalid_anchors=("invalid_anchors", "first"),
    ).reset_index()
    decisions["valid_spread_m"] = decisions[COL_DATETIME].map(_valid_spread_m(cands)).fillna(0.0)
    decisions["decision"] = np.select(
        [
            decisions["invalid_anchors"],
            decisions["n_valid"] == 0,
            decisions["n_valid"] == 1,
            decisions["valid_spread_m"] > t.ambiguous_duplicate_spread_m,
        ],
        ["invalid_anchors", "no_valid", "single_valid", "ambiguous"],
        default="tie_break",
    )
    decisions = decisions.drop(columns="invalid_anchors")

    def rows_of(decision_names: list[str], valid_only: bool | None = None) -> np.ndarray:
        times = decisions.loc[decisions["decision"].isin(decision_names), COL_DATETIME]
        mask = cands[COL_DATETIME].isin(times)
        if valid_only is not None:
            mask &= cands["valid"] == valid_only
        return cands.loc[mask, "row"].to_numpy()

    resolved = ["single_valid", "tie_break"]
    # tốc độ nhỏ nhất trước; hoà thì row nhỏ nhất = ưu tiên cao nhất (work đã sort
    # theo altitude hợp lệ, rồi thứ tự trong file)
    keep_rows = (
        cands[cands["row"].isin(rows_of(resolved, valid_only=True))]
        .sort_values(["score", "row"])
        .groupby(COL_DATETIME)["row"].first().to_numpy()
    )
    quarantined = _concat_quarantine([
        _as_quarantine(work.loc[rows_of(["invalid_anchors"])], REASON_DUPLICATE_INVALID_ANCHORS),
        _as_quarantine(work.loc[rows_of(["no_valid"])], REASON_DUPLICATE),
        _as_quarantine(work.loc[rows_of(["ambiguous"])], REASON_DUPLICATE_AMBIGUOUS),
        _as_quarantine(work.loc[rows_of(resolved, valid_only=False)], REASON_DUPLICATE_REJECTED),
    ])

    drop_rows = np.setdiff1d(cand_idx, keep_rows)
    kept = work.drop(index=drop_rows).reset_index(drop=True)
    return kept, quarantined, decisions


def resolve_duplicate_timestamps(
    df: pd.DataFrame,
    thresholds: CleaningThresholds = DEFAULT_THRESHOLDS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Loại bản ghi trùng mốc thời gian (xem _resolve_duplicate_groups).

    Cần thiết vì trùng timestamp -> dt = 0 -> lỗi chia 0 khi tính speed.

    Returns:
        (kept, quarantined) - quarantined theo schema QUARANTINE_COLS.
    """
    kept, quarantined, _ = _resolve_duplicate_groups(df, thresholds)
    return kept, quarantined


# Stage 3b - Remove speed spikes
def remove_speed_spikes(
    df: pd.DataFrame,
    thresholds: CleaningThresholds = DEFAULT_THRESHOLDS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Loại điểm "gai": nhảy ra xa rồi quay lại ngay.

    Điểm i là gai khi CẢ 3 điều kiện đúng:
      - tốc độ (i-1 -> i)   > impossible_speed_kmh
      - tốc độ (i -> i+1)   > impossible_speed_kmh
      - tốc độ (i-1 -> i+1) <= impossible_speed_kmh (2 hàng xóm gần nhau)

    Điều kiện 3 giữ nguyên các chuỗi di chuyển nhanh liên tục (không phải gai).
    Với lỗi xen kẽ 2 vị trí A-B-A-B (user 025, 062) mọi điểm trong vùng đều
    thoả 3 điều kiện nên cả vùng bị loại - không đoán chuỗi nào đúng.
    Điểm đầu/cuối (thiếu 1 hàng xóm) không bị xét.

    Yêu cầu: mốc thời gian đã duy nhất (chạy sau resolve_duplicate_timestamps).

    Returns:
        (kept, quarantined) - quarantined theo schema QUARANTINE_COLS.
    """
    t = thresholds
    df = df.sort_values(COL_DATETIME, kind="stable").reset_index(drop=True)
    if len(df) < 3:
        return df, _as_quarantine(df.iloc[0:0], REASON_SPIKE)

    ts = df[COL_DATETIME].to_numpy(dtype="datetime64[ns]")
    lat = df[COL_LAT].to_numpy(dtype=float)
    lon = df[COL_LON].to_numpy(dtype=float)
    prev, mid, nxt = slice(None, -2), slice(1, -1), slice(2, None)

    v_in = _speed_kmh(lat[prev], lon[prev], ts[prev], lat[mid], lon[mid], ts[mid])
    v_out = _speed_kmh(lat[mid], lon[mid], ts[mid], lat[nxt], lon[nxt], ts[nxt])
    v_skip = _speed_kmh(lat[prev], lon[prev], ts[prev], lat[nxt], lon[nxt], ts[nxt])

    spike = np.zeros(len(df), dtype=bool)
    spike[1:-1] = (
        (v_in > t.impossible_speed_kmh)
        & (v_out > t.impossible_speed_kmh)
        & (v_skip <= t.impossible_speed_kmh)
    )
    return (
        df[~spike].reset_index(drop=True),
        _as_quarantine(df[spike], REASON_SPIKE),
    )


# Stage 4 - Clean altitude
def clean_altitude(
    df: pd.DataFrame,
    thresholds: CleaningThresholds = DEFAULT_THRESHOLDS,
) -> pd.DataFrame:
    """
    Xử lý cột altitude:
      1. Thay sentinel -777 -> NaN
      2. Nhân 0.3048 để đổi feet -> mét
      3. Nội suy tuyến tính các điểm NaN
      4. Bổ sung fill backward/forward cho điểm đầu/cuối còn thiếu
    """
    t = thresholds
    df = df.copy()

    mask_invalid = df[COL_ALTITUDE_RAW] == t.altitude_invalid
    df.loc[mask_invalid, COL_ALTITUDE_RAW] = np.nan

    df[COL_ALTITUDE_M] = df[COL_ALTITUDE_RAW] * t.altitude_to_meters
    df[COL_ALTITUDE_M] = df[COL_ALTITUDE_M].interpolate(method="linear")
    df[COL_ALTITUDE_M] = df[COL_ALTITUDE_M].ffill().bfill()

    return df


# Haversine vectorized
_EARTH_RADIUS_M = 6_371_000.0  # metres


def _haversine_vectorized(
    lat1: np.ndarray, lon1: np.ndarray,
    lat2: np.ndarray, lon2: np.ndarray,
) -> np.ndarray:
    """Vectorized Haversine: khoảng cách (mètres) giữa các cặp điểm GPS."""
    p1 = np.radians(lat1)
    p2 = np.radians(lat2)
    dp = np.radians(lat2 - lat1)
    dl = np.radians(lon2 - lon1)

    a = (
        np.sin(dp / 2.0) ** 2
        + np.cos(p1) * np.cos(p2) * np.sin(dl / 2.0) ** 2
    )
    a = np.clip(a, 0.0, 1.0)  # tránh lỗi arcsin do floating-point
    return 2.0 * _EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


# Stage 6 - Segment trajectory
def segment_trajectories(
    df: pd.DataFrame,
    thresholds: CleaningThresholds = DEFAULT_THRESHOLDS,
) -> pd.DataFrame:
    """
    Chia quỹ đạo thành các segment (sub_trip_id). Cắt segment mới tại điểm i khi:
      - dt(i-1 -> i) > max_gap_seconds (notebooks/03_segment_gap_threshold.ipynb), hoặc
      - tốc độ(i-1 -> i) > impossible_speed_kmh: bước nhảy không thể là di chuyển
        thật nhưng không xác định được phía nào sai (khối lệch dài tới 9,447
        điểm / 15 giờ, hoặc lệch một phía) -> giữ điểm, chỉ ngắt nối.

    Thuật toán: cumsum các điểm cắt.
    """
    t = thresholds
    df = df.copy().sort_values(COL_DATETIME).reset_index(drop=True)

    if len(df) < 2:
        df[COL_SUB_TRIP_ID] = 0
        return df

    ts = df[COL_DATETIME].to_numpy(dtype="datetime64[ns]")
    lat = df[COL_LAT].to_numpy(dtype=float)
    lon = df[COL_LON].to_numpy(dtype=float)
    dt_s = (ts[1:] - ts[:-1]) / np.timedelta64(1, "s")
    speed = _speed_kmh(lat[:-1], lon[:-1], ts[:-1], lat[1:], lon[1:], ts[1:])

    is_new = np.zeros(len(df), dtype=bool)
    is_new[1:] = (dt_s > t.max_gap_seconds) | (speed > t.impossible_speed_kmh)
    df[COL_SUB_TRIP_ID] = np.cumsum(is_new)

    return df


def recheck_invalid_anchor_groups(
    df: pd.DataFrame,
    quarantined: pd.DataFrame,
    thresholds: CleaningThresholds = DEFAULT_THRESHOLDS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Xử lý lại các nhóm trùng bị quarantine vì 2 điểm neo cách nhau bất khả thi
    (REASON_DUPLICATE_INVALID_ANCHORS), SAU khi đã loại điểm gai.

    Bước xử lý trùng chạy trước bước loại điểm gai, nên điểm neo có thể chính là
    một điểm gai. Với mỗi nhóm như vậy, lấy 2 điểm neo mới từ ``df`` (đã loại
    gai) rồi chạy lại đúng quy tắc của _resolve_duplicate_groups trên khung
    [điểm neo trước, các ứng viên, điểm neo sau]. Nhóm vẫn không phân định được
    thì giữ nguyên trong quarantine. Không xoá thêm điểm neo nào: chỉ quy tắc
    điểm gai (đã có bằng chứng) được phép loại điểm neo. Kiểm chứng:
    notebooks/02_duplicate_timestamps.ipynb mục 3.3 (13/16 nhóm cứu được).

    Returns:
        (df, quarantined) đã cập nhật.
    """
    t = thresholds
    is_bad = quarantined[COL_REASON] == REASON_DUPLICATE_INVALID_ANCHORS
    if not is_bad.any():
        return df, quarantined

    df = df.sort_values(COL_DATETIME, kind="stable").reset_index(drop=True)
    ts = df[COL_DATETIME].to_numpy(dtype="datetime64[ns]")
    rescued, requarantined = [], []
    for when, group in quarantined[is_bad].groupby(COL_DATETIME, sort=False):
        i = int(np.searchsorted(ts, np.datetime64(when)))
        if i == 0 or i == len(df):          # thiếu 1 điểm neo -> không kiểm lại được
            requarantined.append(group)
            continue
        frame = pd.concat(
            [df.iloc[[i - 1]], group.drop(columns=COL_REASON), df.iloc[[i]]], ignore_index=True
        )
        kept, q, _ = _resolve_duplicate_groups(frame, t)
        rescued.append(kept[kept[COL_DATETIME] == when])
        requarantined.append(q)

    df = (
        pd.concat([df, *[r for r in rescued if len(r)]], ignore_index=True)
        .sort_values(COL_DATETIME, kind="stable")
        .reset_index(drop=True)
    )
    return df, _concat_quarantine([quarantined[~is_bad], *requarantined])


def _concat_quarantine(parts: list[pd.DataFrame]) -> pd.DataFrame:
    """Gộp các khung quarantine, bỏ khung rỗng (tránh cảnh báo dtype của pandas)."""
    parts = [p for p in parts if len(p)]
    if not parts:
        return pd.DataFrame(columns=QUARANTINE_COLS)
    return pd.concat(parts, ignore_index=True)


def clean_trajectory(
    plt_path: Path | str,
    user_id: str,
    thresholds: CleaningThresholds | None = None,
) -> tuple[pd.DataFrame | None, pd.DataFrame]:
    """
    Làm sạch MỘT file .plt - pipeline duy nhất, đầu vào cho stay-point detection
    và classifier.

    Steps:
      1. load_plt_file
      2. filter_physical_bounds
      3. resolve_duplicate_timestamps  - quarantine nhóm không phân định được
      4. remove_speed_spikes           - quarantine điểm gai
         + recheck_invalid_anchor_groups - nhóm trùng có điểm neo là điểm gai
           được xử lý lại với điểm neo mới
      5. clean_altitude                - -777 -> mét
      6. segment_trajectories          - cắt gap > 20 phút hoặc bước nhảy > 1100 km/h
      7. localize_by_location          - GMT -> giờ địa phương theo múi giờ của toạ độ
                                         (tz_name, timestamp_local naive)

    Returns:
        (df, quarantined)
        df: columns user_id, source_file, datetime, timestamp_local, tz_name, lat,
            lon, altitude, altitude_m, sub_trip_id - hoặc None nếu file không đọc
            được / không đủ điểm.
        quarantined: các dòng bị loại ở bước 3-4 (schema QUARANTINE_COLS).
    """
    from gps.data.timezone import localize_by_location

    t = thresholds or DEFAULT_THRESHOLDS

    df = load_plt_file(plt_path)
    if df is None or df.empty:
        return None, _concat_quarantine([])

    df[COL_USER_ID] = user_id
    df[COL_SOURCE_FILE] = Path(plt_path).name

    df = filter_physical_bounds(df, t)
    if len(df) < t.min_points:
        return None, _concat_quarantine([])

    df, q_dup = resolve_duplicate_timestamps(df, t)
    df, q_spike = remove_speed_spikes(df, t)
    df, q_dup = recheck_invalid_anchor_groups(df, q_dup, t)
    quarantined = _concat_quarantine([q_dup, q_spike])
    if len(df) < t.min_points:
        return None, quarantined

    df = clean_altitude(df, t)
    df = segment_trajectories(df, t)
    df = _make_sub_trip_id(df, user_id, Path(plt_path).stem)
    df = localize_by_location(df, column=COL_DATETIME, output_column=COL_TIMESTAMP_LOCAL, tz_column=COL_TZ_NAME)

    output_cols = [
        COL_USER_ID, COL_SOURCE_FILE, COL_DATETIME, COL_TIMESTAMP_LOCAL, COL_TZ_NAME,
        COL_LAT, COL_LON, COL_ALTITUDE_RAW, COL_ALTITUDE_M,
        COL_SUB_TRIP_ID,
    ]
    return df[output_cols].reset_index(drop=True), quarantined


def _make_sub_trip_id(
    df: pd.DataFrame,
    user_id: str,
    plt_stem: str,
) -> pd.DataFrame:
    """
    Gán sub_trip_id DUY NHẤT TOÀN CỤC:
      f"{user_id}_{plt_stem}_{segment}"

    Đảm bảo không bao giờ trùng ID giữa các user hoặc giữa các file .plt
    khác nhau của cùng một user.
    """
    prefix = f"{user_id}_{plt_stem}_"
    df[COL_SUB_TRIP_ID] = prefix + df[COL_SUB_TRIP_ID].astype(str)
    return df


# Worker - pickle-able, chạy trong ProcessPoolExecutor
def _process_single_file(
    args: tuple[Path, str, CleaningThresholds],
) -> tuple[pd.DataFrame | None, pd.DataFrame]:
    """
    Args:
        args[0]: plt_path   - đường dẫn file .plt
        args[1]: user_id    - user ID (string)
        args[2]: thresholds

    Returns:
        (df hoặc None, quarantined) - xem clean_trajectory.
    """
    plt_path, user_id, thresholds = args
    return clean_trajectory(plt_path, user_id, thresholds)


def _process_single_user(
    user_id: str,
    plt_paths: list[Path],
    n_workers: int,
    thresholds: CleaningThresholds = DEFAULT_THRESHOLDS,
) -> tuple[list[pd.DataFrame], list[pd.DataFrame]]:
    """
    Xử lý tất cả .plt của MỘT user bằng ProcessPoolExecutor nội bộ user.

    Args:
        user_id     : ID của user (string)
        plt_paths   : Danh sách đường dẫn file .plt của user này
        n_workers   : Số worker cho ProcessPoolExecutor
        thresholds  : ngưỡng thuật toán

    Returns:
        (các DataFrame đã xử lý, các DataFrame quarantine) - có thể rỗng.
    """
    tasks = [(plt_path, user_id, thresholds) for plt_path in plt_paths]

    user_dfs: list[pd.DataFrame] = []
    quarantine_dfs: list[pd.DataFrame] = []
    failed = 0

    # ProcessPoolExecutor riêng cho user này
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = [executor.submit(_process_single_file, task) for task in tasks]

        for future in as_completed(futures):
            try:
                df_result, quarantined = future.result()
            except Exception as exc:
                log.debug("  User %s: lỗi xử lý file: %s", user_id, exc)
                failed += 1
                continue
            if len(quarantined):
                quarantine_dfs.append(quarantined)
            if df_result is not None and not df_result.empty:
                user_dfs.append(df_result)
            else:
                failed += 1

    if failed > 0:
        log.debug("  User %s: %d/%d file thất bại.", user_id, failed, len(tasks))

    return user_dfs, quarantine_dfs


def _write_single_user_parquet(
    user_id: str,
    user_dfs: list[pd.DataFrame],
    output_dir: Path,
) -> int:
    """
    Ghi các DataFrame của một user thành 1 file parquet.

    Args:
        user_id     : ID của user
        user_dfs    : List các DataFrame đã xử lý của user
        output_dir  : Thư mục output

    Returns:
        Số dòng đã ghi
    """
    if not user_dfs:
        return 0

    # Concatenate chỉ những file của user này - RAM chỉ chứa 1 user tại 1 thời điểm
    df_user = pd.concat(user_dfs, ignore_index=True)
    total_rows = len(df_user)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"user_{user_id}.parquet"

    # Sử dụng pyarrow trực tiếp để kiểm soát memory tốt hơn
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.Table.from_pandas(df_user)
    with pa.OSFile(str(out_path), 'wb') as f:
        pq.write_table(
            table,
            f,
            compression='snappy',
            use_dictionary=True,
        )

    log.debug(
        "  Đã ghi user %s: %d dòng -> %s (%.1f MB)",
        user_id, len(df_user), out_path.name, out_path.stat().st_size / 1e6,
    )

    return total_rows


def _write_single_user_quarantine(
    user_id: str,
    quarantine_dfs: list[pd.DataFrame],
    quarantine_dir: Path,
) -> int:
    """Ghi các dòng bị loại ở bước trùng timestamp / điểm gai của 1 user ra CSV
    để soát tay. Trả về số dòng đã ghi (0 nếu không có gì để ghi)."""
    df_q = _concat_quarantine(quarantine_dfs)
    if df_q.empty:
        return 0
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    df_q.sort_values([COL_SOURCE_FILE, COL_DATETIME]).to_csv(
        quarantine_dir / f"user_{user_id}.csv", index=False,
    )
    return len(df_q)


def _find_users(data_dir: Path) -> dict[str, list[Path]]:
    """user_id -> các file .plt. Hỗ trợ data_dir là thư mục của 1 user
    (data_dir/Trajectory/*.plt) hoặc thư mục chứa nhiều user (data_dir/010/...)."""
    if (data_dir / "Trajectory").exists():
        user_dirs = [data_dir]
    else:
        user_dirs = [d for d in sorted(data_dir.iterdir()) if d.is_dir() and d.name.isdigit()]
    users = {}
    for user_dir in user_dirs:
        plt_paths = sorted((user_dir / "Trajectory").glob("*.plt"))
        if plt_paths:
            users[user_dir.name] = plt_paths
    return users


def process_all_trajectories(
    data_dir: Path | str,
    output_dir: Path | str | None = None,
    n_workers: int | None = None,
    thresholds: CleaningThresholds = DEFAULT_THRESHOLDS,
    max_users: int | None = None,
) -> dict:
    """
    Làm sạch toàn bộ file .plt trong data_dir - TUẦN TỰ THEO USER.

    Chống tràn RAM & quá nhiệt CPU:
      1. Duyệt tuần tự từng User folder (user 000, 001, ...)
      2. Với mỗi user, dùng ProcessPoolExecutor xử lý các file .plt của user đó
      3. Ngay khi user xong: Gộp -> Lưu parquet -> gc.collect() -> sang user tiếp
      4. n_workers = min(4, os.cpu_count())

    Args:
        data_dir   : thư mục chứa các folder user (000/, 001/, ...) hoặc thư mục
                     của 1 user
        output_dir : thư mục chứa các file user_*.parquet
                     [default: data_dir.parent/processed/users/]
                     Điểm bị loại được ghi vào output_dir.parent/quarantine/
        n_workers  : số CPU worker (mặc định: min(4, os.cpu_count()))
        thresholds : ngưỡng thuật toán
        max_users  : chỉ xử lý N user đầu tiên (mặc định: tất cả)

    Returns:
        Dict tổng kết với keys: total_rows, n_users, n_quarantined, output_dir
        ({} nếu không tìm thấy file .plt nào).
    """
    data_dir = Path(data_dir)
    output_dir = Path(output_dir) if output_dir is not None else data_dir.parent / "processed" / "users"
    if n_workers is None:
        n_workers = min(4, os.cpu_count() or 4)

    log.info("=== Xử lý tuần tự theo User ===")
    log.info("  n_workers = %d (max 4, tránh quá nhiệt)", n_workers)
    log.info("  output_dir = %s", output_dir)

    users = _find_users(data_dir)
    total_users = len(users)
    if total_users == 0:
        log.error("Không tìm thấy User folder nào với file .plt trong %s.", data_dir)
        return {}
    if max_users is not None and max_users > 0:
        users = dict(sorted(users.items())[:max_users])
        log.info("Giới hạn xử lý: %d/%d users (max_users=%d)", len(users), total_users, max_users)
    log.info("Tìm thấy %d users, tổng %d file .plt.", len(users), sum(map(len, users.values())))

    output_dir.mkdir(parents=True, exist_ok=True)
    quarantine_dir = output_dir.parent / "quarantine"
    total_rows = 0
    total_quarantined = 0
    processed_users = 0

    for k, (user_id, plt_paths) in enumerate(sorted(users.items()), start=1):
        log.info("[%d/%d] Xử lý User %s (%d file) ...", k, len(users), user_id, len(plt_paths))

        user_dfs, quarantine_dfs = _process_single_user(
            user_id=user_id,
            plt_paths=plt_paths,
            n_workers=n_workers,
            thresholds=thresholds,
        )

        n_q = _write_single_user_quarantine(user_id, quarantine_dfs, quarantine_dir)
        total_quarantined += n_q
        if n_q:
            log.info("  User %s: %d điểm bị đưa vào quarantine.", user_id, n_q)

        if not user_dfs:
            log.warning("  User %s: không có file nào xử lý thành công.", user_id)
            continue

        user_rows = _write_single_user_parquet(user_id, user_dfs, output_dir)
        total_rows += user_rows

        # Giải phóng RAM ngay sau mỗi user
        del user_dfs
        gc.collect()

        log.info("  User %s: %d dòng đã ghi. RAM đã giải phóng.", user_id, user_rows)
        processed_users += 1

    parquet_files = list(output_dir.glob("user_*.parquet"))
    total_size_mb = sum(f.stat().st_size for f in parquet_files) / 1e6
    log.info("=== HOÀN TẤT ===")
    log.info("  Users xử lý thành công: %d/%d", processed_users, len(users))
    log.info("  Tổng dòng GPS: %d", total_rows)
    log.info("  Tổng kích thước: %.1f MB", total_size_mb)
    log.info("  Điểm quarantine: %d (-> %s)", total_quarantined, quarantine_dir)

    return {
        "total_rows": total_rows,
        "n_users": processed_users,
        "n_quarantined": total_quarantined,
        "output_dir": output_dir,
    }


# CLI - argparse entry point
def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m gps.data.processing",
        description="GeoLife GPS Cleaning Pipeline - .plt thô -> partitioned Parquet sạch.",
    )
    p.add_argument(
        "--data-dir", "-d",
        type=Path,
        default=Path("data/Geolife Trajectories 1.3/Data"),
        help="Thư mục chứa folder user (000/, 001/, ...) "
             "[default: data/Geolife Trajectories 1.3/Data]",
    )
    p.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=None,
        help="Thư mục output cho partitioned parquet "
             "[default: <data-dir>/../processed/users/]",
    )
    p.add_argument(
        "--workers", "-w",
        type=int,
        default=None,
        help="Số CPU worker [default: min(4, os.cpu_count())]",
    )
    p.add_argument(
        "--gap-seconds",
        type=float,
        default=1200.0,
        help="Ngưỡng cắt segment, giây [default: 1200 = 20 phút]",
    )
    p.add_argument(
        "--max-users",
        type=int,
        default=None,
        help="Giới hạn số user xử lý (mặc định: tất cả). "
             "VD: --max-users 50 để chỉ xử lý 50 user đầu tiên.",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Bật log DEBUG",
    )
    return p


if __name__ == "__main__":
    parser = _build_argparser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    start = datetime.now()
    result = process_all_trajectories(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        n_workers=args.workers,
        thresholds=CleaningThresholds(max_gap_seconds=args.gap_seconds),
        max_users=args.max_users,
    )
    elapsed = (datetime.now() - start).total_seconds()

    if not result:
        log.error("Pipeline không tạo được output.")
        sys.exit(1)
    log.info("TỔNG KẾT:")
    log.info("  Tổng điểm GPS:    %s", f"{result['total_rows']:,}")
    log.info("  Số users:          %d", result["n_users"])
    log.info("  Điểm quarantine:   %d", result["n_quarantined"])
    log.info("  Output dir:        %s", result["output_dir"])
    log.info("  Thời gian xử lý:  %.1f s (%.1f phút)", elapsed, elapsed / 60)
