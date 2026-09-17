"""Test cleaner.py with a real GeoLife .plt file."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from src.data.cleaner import GPSCleaner, CleaningConfig

DATA_DIR = PROJECT_ROOT / "data" / "Geolife Trajectories 1.3" / "Data" / "000" / "Trajectory"


def load_plt(filepath: Path) -> pd.DataFrame:
    """Load a single .plt file into a DataFrame."""
    df = pd.read_csv(
        filepath,
        skiprows=6,
        header=None,
        names=["lat", "lng", "unused", "altitude", "date_num", "date", "time"],
    )
    df["timestamp"] = pd.to_datetime(df["date"] + " " + df["time"])
    return df[["lat", "lng", "timestamp"]]


def main() -> None:
    plt_files = sorted(DATA_DIR.glob("*.plt"))
    if not plt_files:
        print(f"No .plt files found at {DATA_DIR}")
        return

    sample = plt_files[0]
    print(f"Testing with: {sample.name}")

    df = load_plt(sample)
    print(f"  Raw points: {len(df)}")

    cleaner = GPSCleaner(CleaningConfig())
    df_clean = cleaner.clean_trajectory(df)
    print(f"  After clean: {len(df_clean)} (removed {len(df) - len(df_clean)})")

    # Compute speeds to verify they're plausible
    if len(df_clean) > 1:
        from src.data.cleaner import GPSCleaner as GC
        speed_stats = []
        for i in range(1, len(df_clean)):
            d = GC.haversine_distance(
                df_clean.iloc[i - 1]["lat"], df_clean.iloc[i - 1]["lng"],
                df_clean.iloc[i]["lat"], df_clean.iloc[i]["lng"],
            )
            t = (df_clean.iloc[i]["timestamp"] - df_clean.iloc[i - 1]["timestamp"]).total_seconds()
            speed_stats.append(GC.calculate_speed(d, t))
        speed_stats = np.array(speed_stats)
        print(f"  Speed stats: median={np.median(speed_stats):.1f} km/h, "
              f"max={speed_stats.max():.1f} km/h, p99={np.percentile(speed_stats, 99):.1f} km/h")

    segments = cleaner.split_by_gaps(df_clean)
    print(f"  Segments after splitting by gaps: {len(segments)}")
    for i, seg in enumerate(segments[:3]):
        print(f"    Segment {i}: {len(seg)} points "
              f"({seg['timestamp'].min()} → {seg['timestamp'].max()})")


if __name__ == "__main__":
    main()
