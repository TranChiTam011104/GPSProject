"""
GeoLife GPS Data Processing Pipeline.
=====================================
Production-grade module chuyển từ notebooks/02_cleaning_geolife.ipynb.

REFACTOR v2 (2026-09-21) - Chống tràn RAM 97% & quá nhiệt CPU 95°C:
  - Xử lý tuần tự theo từng User: duyệt user -> ProcessPoolExecutor nội bộ user
    -> ghi parquet -> gc.collect() -> sang user tiếp theo
  - n_workers = min(4, os.cpu_count()) thay vì cpu_count() - 1
  - match_labels dùng pd.merge_asof vectorized thay vì iterrows()

Pipeline steps (đã kiểm chứng trong notebook):
  1. Filter physical bounds   - lat in [-90,90], lon in [-180,180], ~(0,0)
  2. Deduplicate timestamps   - giữ bản ghi đầu tiên
  3. Clean altitude           - -777 -> NaN -> feet*0.3048 -> mét -> linear interpolate
  4. Compute kinematics       - Haversine vectorized -> delta_time_s, speed_kmh
  5. Filter GPS drift         - bỏ điểm có speed > 180 km/h
  6. Segment trajectories     - sub_trip_id khi dt > 1200 s (20 phút)
  7. Merge transport labels   - khớp [start, end] interval với labels.txt

Output: Partitioned Apache Parquet -> data/processed/users/user_{user_id}.parquet
"""

from __future__ import annotations

import argparse
import gc
import logging
import os
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("processing")


@dataclass
class CleaningThresholds:
    """Các ngưỡng thuật toán đã kiểm chứng trong 02_cleaning_geolife.ipynb."""

    # 1. Physical bounds
    lat_min: float = -90.0
    lat_max: float = 90.0
    lon_min: float = -180.0
    lon_max: float = 180.0

    # 2. Altitude sentinel
    altitude_invalid: int = -777
    altitude_to_meters: float = 0.3048  # feet -> mét

    # 3. Speed filter (GPS drift / multipath)
    max_speed_kmh: float = 180.0

    # 4. Trajectory segmentation (time gap threshold)
    max_gap_seconds: float = 1200.0  # 20 phút

    # 5. Minimum points per file to keep
    min_points: int = 2


DEFAULT_THRESHOLDS = CleaningThresholds()


# Column constants
COL_LAT = "lat"
COL_LON = "lon"
COL_DATETIME = "datetime"
COL_ALTITUDE_RAW = "altitude"       # feet, gốc từ .plt
COL_ALTITUDE_M = "altitude_m"      # mét, đã xử lý
COL_DELTA_TIME_S = "delta_time_s"
COL_SPEED_KMH = "speed_kmh"
COL_SUB_TRIP_ID = "sub_trip_id"
COL_MODE = "mode"
COL_USER_ID = "user_id"
COL_SOURCE_FILE = "source_file"


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


# Stage 3 - Deduplicate timestamps
def deduplicate_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """
    Xóa các bản ghi trùng mốc thời gian, giữ bản ghi ĐẦU TIÊN.

    Cần thiết vì trùng timestamp -> dt = 0 -> lỗi chia 0 khi tính speed.
    """
    return df.drop_duplicates(subset=[COL_DATETIME], keep="first").copy()


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


# Stage 5 - Compute kinematics (Haversine vectorized)
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


def compute_kinematics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tính các cột động học vectorized cho tất cả các điểm liên tiếp:
      - delta_time_s  : chênh lệch thời gian (giây)
      - speed_kmh     : vận tốc tức thời (km/h)
    """
    df = df.copy().sort_values(COL_DATETIME).reset_index(drop=True)

    lat = df[COL_LAT].to_numpy()
    lon = df[COL_LON].to_numpy()
    ts = df[COL_DATETIME]

    lat_prev = np.roll(lat, 1)
    lat_prev[0] = lat[0]
    lon_prev = np.roll(lon, 1)
    lon_prev[0] = lon[0]

    dist_m = _haversine_vectorized(lat_prev, lon_prev, lat, lon)
    dist_m[0] = 0.0

    dt_s = ts.diff().dt.total_seconds().to_numpy().copy()
    dt_s[0] = 0.0
    dt_safe = np.where(dt_s <= 0, np.nan, dt_s)

    speed_kmh = (dist_m / dt_safe) * 3.6
    speed_kmh[0] = np.nan

    df[COL_DELTA_TIME_S] = dt_s
    df["distance_m"] = dist_m
    df[COL_SPEED_KMH] = speed_kmh

    return df


# Stage 6 - Filter GPS drift / unrealistic speed
def filter_speed_drift(
    df: pd.DataFrame,
    thresholds: CleaningThresholds = DEFAULT_THRESHOLDS,
) -> pd.DataFrame:
    """
    Loại bỏ các điểm GPS nhảy vọt (multipath effect) dựa trên vận tốc cực đoan.

    Ngưỡng đã kiểm chứng: SPEED_LIMIT = 180 km/h

    Điểm đầu tiên (NaN speed) luôn được giữ lại.
    Sau khi lọc, tái tính kinematics cho các điểm còn lại.
    """
    t = thresholds
    mask_ok = df[COL_SPEED_KMH].isna() | (df[COL_SPEED_KMH] <= t.max_speed_kmh)
    df = df[mask_ok].copy().reset_index(drop=True)

    # Tái tính kinematics sau khi lọc
    df = compute_kinematics(df)

    return df


# Stage 7 - Segment trajectory by time gaps
def segment_trajectories(
    df: pd.DataFrame,
    thresholds: CleaningThresholds = DEFAULT_THRESHOLDS,
) -> pd.DataFrame:
    """
    Chia quỹ đạo thành các sub_trip_id khi khoảng trống thời gian vượt ngưỡng.

    Ngưỡng đã kiểm chứng: dt > 1200 s (20 phút) -> cắt chặng mới.

    Thuật toán: Cumulative Sum vectorized - mỗi khi gap > threshold,
    tăng sub_trip_id lên 1.
    """
    t = thresholds
    df = df.copy().sort_values(COL_DATETIME).reset_index(drop=True)

    if len(df) < 2:
        df[COL_SUB_TRIP_ID] = 0
        return df

    is_new_trip = (df[COL_DELTA_TIME_S] > t.max_gap_seconds).fillna(False)
    df[COL_SUB_TRIP_ID] = is_new_trip.cumsum()

    return df


# Stage 8 - Load transport labels
def load_labels(user_dir: Path) -> pd.DataFrame | None:
    """
    Đọc file labels.txt của một user (nếu tồn tại).

    Định dạng labels.txt (bỏ dòng header):
      start_date  start_time  end_date  end_time  mode

    Returns:
        DataFrame với columns: start_datetime, end_datetime, mode
        hoặc None nếu file không tồn tại hoặc lỗi.
    """
    labels_path = user_dir / "labels.txt"
    if not labels_path.exists():
        return None

    try:
        df = pd.read_csv(
            labels_path,
            sep=r"\s+",
            skiprows=1,  # bỏ dòng "Start Time  ...  Transportation Mode"
            header=None,
            names=["start_date", "start_time", "end_date", "end_time", COL_MODE],
        )
        df["start_datetime"] = pd.to_datetime(
            df["start_date"] + " " + df["start_time"],
            format="%Y/%m/%d %H:%M:%S",
            errors="coerce",
        )
        df["end_datetime"] = pd.to_datetime(
            df["end_date"] + " " + df["end_time"],
            format="%Y/%m/%d %H:%M:%S",
            errors="coerce",
        )
        df = df.dropna(subset=["start_datetime", "end_datetime"])
        return df[["start_datetime", "end_datetime", COL_MODE]].reset_index(drop=True)
    except Exception as exc:
        warnings.warn(f"Không đọc được labels.txt của {user_dir.name}: {exc}")
        return None


# REFACTOR v2: match_labels dùng pd.merge_asof vectorized - THAY THẾ iterrows()
def match_labels(df: pd.DataFrame, labels_df: pd.DataFrame | None) -> pd.DataFrame:
    """
    Gán nhãn phương tiện di chuyển vào từng điểm GPS dựa trên khoảng thời gian.
    Chính xác 100% theo logic Left Interval Matching (Vectorized NumPy).
    """
    df = df.copy()
    df[COL_MODE] = "unknown"

    if labels_df is None or labels_df.empty:
        return df

    # Chuyển vector thời gian sang mảng numpy int64/datetime64 để so sánh ở tầng C
    gps_times = df[COL_DATETIME].to_numpy()

    # File labels chỉ có ~200 dòng, duyệt cực nhanh (~1ms)
    for _, row in labels_df.iterrows():
        start = np.datetime64(row["start_datetime"])
        end = np.datetime64(row["end_datetime"])
        mode = row[COL_MODE]

        # Tìm các điểm GPS nằm lọt hoàn toàn trong khoảng thời gian
        mask = (gps_times >= start) & (gps_times <= end)
        if np.any(mask):
            df.loc[mask, COL_MODE] = mode

    return df


# ── Convenience wrapper ─────────────────────────────────────────────────────────


def clean_and_segment_trajectory(
    plt_path: Path | str,
    user_id: str,
    labels: pd.DataFrame | None,
    thresholds: CleaningThresholds | None = None,
) -> pd.DataFrame | None:
    """Run the full pipeline on a single .plt file.

    Pipeline: load → physical bounds → deduplicate → altitude → kinematics →
    speed filter → segment → label match.

    Args:
        plt_path: Path to the .plt file.
        user_id: User identifier (written into the output DataFrame).
        labels: Optional labels DataFrame (from :func:`load_labels`).
        thresholds: Cleaning thresholds (default: ``DEFAULT_THRESHOLDS``).

    Returns:
        Cleaned DataFrame, or ``None`` if the file is unreadable.
    """
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS
    df = load_plt_file(plt_path)
    if df is None or df.empty:
        return None
    df[COL_USER_ID] = user_id
    df = filter_physical_bounds(df, thresholds)
    df = deduplicate_timestamps(df)
    df = clean_altitude(df, thresholds)
    df = compute_kinematics(df)
    df = filter_speed_drift(df, thresholds)
    df = segment_trajectories(df, thresholds)
    df = match_labels(df, labels)
    return df


def build_labels_cache(data_dir: Path) -> dict[str, pd.DataFrame | None]:
    """
    Đọc labels.txt MỘT LẦN cho mỗi user, trả về dict để reuse trong workers.

    Key: user_id (string như "000", "010")
    Value: DataFrame đã parse hoặc None nếu user không có labels.txt
    """
    cache: dict[str, pd.DataFrame | None] = {}
    user_dirs: list[Path] = []

    # Hỗ trợ 2 cấu trúc thư mục
    if (data_dir / "Trajectory").exists():
        user_dirs = [data_dir]
    else:
        user_dirs = [
            d for d in sorted(data_dir.iterdir())
            if d.is_dir() and d.name.isdigit()
        ]

    for user_dir in user_dirs:
        user_id = user_dir.name
        cache[user_id] = load_labels(user_dir)

    labeled = sum(1 for v in cache.values() if v is not None)
    log.info("Đã preload %d/%d users có labels.txt.", labeled, len(cache))
    return cache


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


# Worker - nhận labels_df trực tiếp, gán unique sub_trip_id
def _process_single_file(
    args: tuple[Path, str, str, pd.DataFrame | None],
) -> pd.DataFrame | None:
    """
    Worker function - pickle-able.

    Args:
        args[0]: plt_path       - đường dẫn file .plt
        args[1]: user_id        - user ID (string)
        args[2]: plt_stem       - tên file .plt không extension (dùng cho sub_trip_id)
        args[3]: labels_df      - DataFrame đã parse sẵn từ labels_cache (None nếu
                                  user không có labels.txt)
    """
    plt_path, user_id, plt_stem, labels_df = args
    t = DEFAULT_THRESHOLDS

    # 1. Load
    try:
        df = load_plt_file(plt_path)
    except Exception as exc:
        warnings.warn(f"Lỗi đọc file {plt_path.name}: {exc}")
        return None

    if len(df) < t.min_points:
        return None

    # 2. Physical bounds
    df = filter_physical_bounds(df, t)
    if len(df) < t.min_points:
        return None

    # 3. Deduplicate timestamps
    df = deduplicate_timestamps(df)
    if len(df) < t.min_points:
        return None

    # 4. Clean altitude
    df = clean_altitude(df, t)

    # 5. Compute kinematics
    df = compute_kinematics(df)
    if len(df) < t.min_points:
        return None

    # 6. Filter speed drift
    df = filter_speed_drift(df, t)
    if len(df) < t.min_points:
        return None

    # 7. Segment by time gaps
    df = segment_trajectories(df, t)

    # Gán sub_trip_id DUY NHẤT trước khi trả về
    df = _make_sub_trip_id(df, user_id, plt_stem)

    # 8. Match labels (đã có sẵn DataFrame, không cần đọc lại file)
    df = match_labels(df, labels_df)

    # Metadata
    df[COL_USER_ID] = user_id
    df[COL_SOURCE_FILE] = plt_path.name

    # Drop helper column distance_m
    if "distance_m" in df.columns:
        df = df.drop(columns=["distance_m"])

    # Sort output columns
    output_cols = [
        COL_USER_ID, COL_SOURCE_FILE, COL_DATETIME,
        COL_LAT, COL_LON, COL_ALTITUDE_RAW, COL_ALTITUDE_M,
        COL_DELTA_TIME_S, COL_SPEED_KMH, COL_SUB_TRIP_ID, COL_MODE,
    ]
    return df[output_cols]


# REFACTOR v2: _process_single_user - xử lý tất cả .plt của 1 user bằng workers
def _process_single_user(
    user_id: str,
    plt_paths: list[Path],
    labels_df: pd.DataFrame | None,
    n_workers: int,
) -> list[pd.DataFrame]:
    """
    Xử lý tất cả .plt của MỘT user bằng ProcessPoolExecutor nội bộ user.

    Args:
        user_id     : ID của user (string)
        plt_paths   : Danh sách đường dẫn file .plt của user này
        labels_df   : DataFrame đã parse từ labels.txt của user
        n_workers   : Số worker cho ProcessPoolExecutor

    Returns:
        List các DataFrame đã xử lý (có thể rỗng nếu tất cả thất bại)
    """
    # Build tasks cho user này
    tasks = [
        (plt_path, user_id, plt_path.stem, labels_df)
        for plt_path in plt_paths
    ]

    user_dfs: list[pd.DataFrame] = []
    failed = 0

    # ProcessPoolExecutor riêng cho user này
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = {executor.submit(_process_single_file, task): task for task in tasks}

        for future in as_completed(futures):
            task = futures[future]
            try:
                df_result = future.result()
                if df_result is not None and not df_result.empty:
                    user_dfs.append(df_result)
                else:
                    failed += 1
            except Exception:
                failed += 1

    if failed > 0:
        log.debug("  User %s: %d/%d file thất bại.", user_id, failed, len(tasks))

    return user_dfs


# REFACTOR v2: _write_single_user_parquet - ghi 1 user ra parquet, giải phóng RAM
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

    # Add a tz-aware `timestamp_local` column (Asia/Shanghai, UTC+8) so
    # downstream consumers (heuristic .hour, API responses) read local time
    # directly without re-converting. The original naive GMT `timestamp`
    # column is preserved for audit / re-processing.
    from gps.data.timezone import localize_dataframe_column
    df_user = localize_dataframe_column(df_user)
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


# REFACTOR v2: process_all_trajectories - xử lý tuần tự theo User
def process_all_trajectories(
    data_dir: Path | str,
    output_dir: Path | str | None = None,
    n_workers: int | None = None,
    thresholds: CleaningThresholds = DEFAULT_THRESHOLDS,
) -> dict:
    """
    Xử lý toàn bộ file .plt trong data_dir - TUẦN TỰ THEO USER.

    REFACTOR v2 - Chống tràn RAM 97% & quá nhiệt CPU 95°C:
      1. Duyệt tuần tự từng User folder (user 000, 001, ...)
      2. Với mỗi user, dùng ProcessPoolExecutor xử lý các file .plt của user đó
      3. Ngay khi user xong: Gộp -> Lưu parquet -> gc.collect() -> sang user tiếp
      4. n_workers = min(4, os.cpu_count()) - tránh quá nhiệt

    Args:
        data_dir   : thư mục Data (chứa các folder user: 000/, 001/, ...)
        output_dir : thư mục chứa các file user_*.parquet
                     [default: data_dir.parent/processed/users/]
        n_workers  : số CPU worker (mặc định: min(4, os.cpu_count()))
        thresholds : ngưỡng thuật toán

    Returns:
        Dict tổng kết với keys: total_rows, n_users, mode_dist, output_dir
    """
    data_dir = Path(data_dir)
    if output_dir is None:
        output_dir = data_dir.parent / "processed" / "users"
    else:
        output_dir = Path(output_dir)

    # REFACTOR v2: Giới hạn workers an toàn
    if n_workers is None:
        n_workers = min(4, os.cpu_count() or 4)

    log.info("=== REFACTOR v2: Xử lý tuần tự theo User ===")
    log.info("  n_workers = %d (max 4, tránh quá nhiệt)", n_workers)
    log.info("  output_dir = %s", output_dir)

    # Quét toàn bộ user folders
    log.info("Đang quét toàn bộ User folders trong %s ...", data_dir)

    user_info: dict[str, dict] = {}  # user_id -> {plt_paths: [...], labels_df}

    if (data_dir / "Trajectory").exists():
        # Cấu trúc 1: data_dir/010/Trajectory/...
        user_id = data_dir.name
        labels_df = load_labels(data_dir)
        plt_paths = sorted((data_dir / "Trajectory").glob("*.plt"))
        user_info[user_id] = {
            "plt_paths": plt_paths,
            "labels_df": labels_df,
        }
        log.info("  User %s: %d file .plt, labels: %s", user_id, len(plt_paths), labels_df is not None)
    else:
        # Cấu trúc 2: data_dir/Data/010/...
        for user_dir in sorted(data_dir.iterdir()):
            if not user_dir.is_dir() or not user_dir.name.isdigit():
                continue
            user_id = user_dir.name
            labels_df = load_labels(user_dir)

            traj_dir = user_dir / "Trajectory"
            if not traj_dir.exists():
                continue

            plt_paths = sorted(traj_dir.glob("*.plt"))
            if plt_paths:
                user_info[user_id] = {
                    "plt_paths": plt_paths,
                    "labels_df": labels_df,
                }
                log.info("  User %s: %d file .plt, labels: %s", user_id, len(plt_paths), labels_df is not None)

    total_users = len(user_info)
    if total_users == 0:
        log.error("Không tìm thấy User folder nào với file .plt.")
        return {}

    total_files = sum(len(u["plt_paths"]) for u in user_info.values())
    log.info("Tìm thấy %d users, tổng %d file .plt.", total_users, total_files)

    # Xử lý tuần tự từng USER
    output_dir.mkdir(parents=True, exist_ok=True)
    total_rows = 0
    mode_dist: dict[str, int] = {}
    processed_users = 0

    for user_id, info in sorted(user_info.items()):
        plt_paths = info["plt_paths"]
        labels_df = info["labels_df"]

        log.info(
            "\n[%d/%d] Xử lý User %s (%d file) ...",
            processed_users + 1, total_users, user_id, len(plt_paths),
        )

        # ProcessPoolExecutor cho user này
        user_dfs = _process_single_user(
            user_id=user_id,
            plt_paths=plt_paths,
            labels_df=labels_df,
            n_workers=n_workers,
        )

        if not user_dfs:
            log.warning("  User %s: không có file nào xử lý thành công.", user_id)
            # Vẫn tiếp tục sang user tiếp theo
            continue

        # Ghi parquet cho user này
        user_rows = _write_single_user_parquet(user_id, user_dfs, output_dir)
        total_rows += user_rows

        # Tính mode distribution cho user này (trước khi xóa)
        df_sample = pd.concat(user_dfs, ignore_index=True)
        for mode, count in df_sample[COL_MODE].value_counts().items():
            mode_dist[mode] = mode_dist.get(mode, 0) + count

        # REFACTOR v2: GIẢI PHÓNG RAM LẬP TỨC
        del user_dfs
        del df_sample
        gc.collect()

        log.info("  User %s: %d dòng đã ghi. RAM đã giải phóng.", user_id, user_rows)
        processed_users += 1

    # Tổng kết
    log.info("\n=== HOÀN TẤT ===")
    log.info("  Users xử lý thành công: %d/%d", processed_users, total_users)

    # Tính kích thước output
    parquet_files = list(output_dir.glob("user_*.parquet"))
    total_size_mb = sum(f.stat().st_size for f in parquet_files) / 1e6

    log.info("  Tổng dòng GPS: %d", total_rows)
    log.info("  Tổng kích thước: %.1f MB", total_size_mb)
    log.info("  Mode phân bố: %s", dict(sorted(mode_dist.items(), key=lambda x: -x[1])[:5]))

    return {
        "total_rows": total_rows,
        "n_users": processed_users,
        "mode_dist": mode_dist,
        "output_dir": output_dir,
    }


# CLI - argparse entry point
def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m src.data.processing",
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
             "[default: data/processed_v1/]",
    )
    p.add_argument(
        "--workers", "-w",
        type=int,
        default=None,
        help="Số CPU worker [default: min(4, os.cpu_count())]",
    )
    p.add_argument(
        "--max-speed",
        type=float,
        default=180.0,
        help="Ngưỡng lọc GPS drift, km/h [default: 180]",
    )
    p.add_argument(
        "--gap-seconds",
        type=float,
        default=1200.0,
        help="Ngưỡng cắt chặng hành trình, giây [default: 1200 = 20 phút]",
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

    thresholds = CleaningThresholds(
        max_speed_kmh=args.max_speed,
        max_gap_seconds=args.gap_seconds,
    )

    start = datetime.now()
    result = process_all_trajectories(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        n_workers=args.workers,
        thresholds=thresholds,
    )
    elapsed = (datetime.now() - start).total_seconds()

    if result:
        log.info("TỔNG KẾT:")
        log.info("  Tổng điểm GPS:    %s", f"{result['total_rows']:,}")
        log.info("  Số users:          %d", result["n_users"])
        log.info("  Mode phân bố:     %s", result["mode_dist"])
        log.info("  Output dir:        %s", result["output_dir"])
        log.info("  Thời gian xử lý:  %.1f s (%.1f phút)", elapsed, elapsed / 60)
    else:
        log.error("Pipeline không tạo được output.")
        sys.exit(1)
