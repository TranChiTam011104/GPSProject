"""GeoLife ``.plt`` file loader (Checkpoint 1 / Tuần 1).

Dataset structure:
    data/
    └── Geolife Trajectories 1.3/
        └── Data/
            ├── 000/
            │   └── Trajectory/
            │       ├── 20081023025304.plt
            │       └── ...
            ├── 001/
            │   └── Trajectory/
            │       └── ...
            └── ...

The first 6 lines of every ``.plt`` file are metadata; data rows start at line 7.
Raw columns (0-indexed after skiprows=6)::
    0  lat          — decimal degrees, WGS84
    1  lon          — decimal degrees, WGS84
    2  reserved     — always 0
    3  altitude     — feet (NOT metres); -777 = missing sensor
    4  date_days    — days since Unix epoch (float)
    5  date_str     — "YYYY-MM-DD"
    6  time_str     — "HH:MM:SS"

Timestamps are kept naive (GMT) — apply :mod:`gps.data.timezone`
before any hour-of-day heuristic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import pandas as pd

# True column names as they appear in the raw file (after skipping 6 header lines).
# Column 3 (altitude) is in **feet** — downstream code must multiply by 0.3048.
_RAW_COLUMNS = ["lat", "lon", "reserved", "altitude", "date_days", "date_str", "time_str"]
SKIP_ROWS = 6


def load_plt(path: Union[str, Path]) -> Optional[pd.DataFrame]:
    """Read a single ``.plt`` file into a DataFrame.

    Returns ``None`` if the file is missing or unreadable so callers can
    pipeline a batch of files without try/except noise.

    Output columns: ``lat``, ``lon``, ``altitude_ft``, ``timestamp`` (naive GMT).
    """
    p = Path(path)
    if not p.is_file():
        return None
    try:
        df = pd.read_csv(p, skiprows=SKIP_ROWS, header=None, names=_RAW_COLUMNS)
    except Exception:
        return None

    if df.empty:
        return df

    # Combine date + time into a naive datetime (GMT — GeoLife convention).
    df["timestamp"] = pd.to_datetime(
        df["date_str"] + " " + df["time_str"],
        errors="coerce",
        format="%Y-%m-%d %H:%M:%S",
    )
    df = df.dropna(subset=["timestamp", "lat", "lon"]).reset_index(drop=True)
    # Return lat, lon, altitude (feet), timestamp.
    # NOTE: altitude is in FEET. Downstream code (clean_altitude) must convert
    # to metres (× 0.3048) and handle the -777 sentinel.
    return df[["lat", "lon", "altitude", "timestamp"]]


# ── Aliases for backward compatibility ────────────────────────────────────────

COLUMN_NAMES = _RAW_COLUMNS  # noqa: N816  (exported for tests / scripts)


class GeoLifeLoader:
    """Convenience wrapper around :func:`load_plt` for batch jobs.

    Expects the standard GeoLife directory layout::

        <data_root>/
        └── Data/          ← auto-appended
            └── {user_id}/
                └── Trajectory/
                    └── *.plt
    """

    # Number of header lines in every GeoLife ``.plt`` file (legacy constant).
    HEADER_LINES = SKIP_ROWS  # noqa: N816

    def __init__(self, data_root: Union[str, Path, None] = None,
                 data_dir: Union[str, Path, None] = None):
        # Accept both ``data_dir=`` (legacy kwarg) and ``data_root=`` (canonical).
        chosen = data_dir if data_dir is not None else data_root
        if chosen is None:
            raise TypeError("GeoLifeLoader requires data_root or data_dir")
        self.data_root = Path(chosen)
        self.data_dir = self.data_root

    def load_user(self, user_id: str) -> list[pd.DataFrame]:
        """Return all trajectories for a user as a list of DataFrames."""
        user_dir = self.data_root / "Data" / user_id / "Trajectory"
        if not user_dir.is_dir():
            return []
        return [
            df
            for plt in sorted(user_dir.glob("*.plt"))
            if (df := load_plt(plt)) is not None
        ]

    def load_all_users(self) -> list[tuple[str, pd.DataFrame]]:
        """Yield (user_id, DataFrame) for every user that has .plt files."""
        data_dir = self.data_root / "Data"
        if not data_dir.is_dir():
            return []
        frames = []
        for user_dir in sorted(data_dir.iterdir()):
            if not user_dir.is_dir():
                continue
            traj_dir = user_dir / "Trajectory"
            if not traj_dir.is_dir():
                continue
            user_id = user_dir.name
            user_dfs = [
                df for plt in sorted(traj_dir.glob("*.plt"))
                if (df := load_plt(plt)) is not None
            ]
            if user_dfs:
                frames.append((user_id, pd.concat(user_dfs, ignore_index=True)))
        return frames
