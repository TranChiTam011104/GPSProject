"""Test cleaner.py with a real GeoLife .plt file."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from gps.data.cleaner import GPSCleaner, CleaningConfig
from gps.data.loader import load_plt


def main() -> None:
    # Test 1: Load with altitude (new feature)
    DATA_DIR = PROJECT_ROOT / "data" / "Geolife Trajectories 1.3" / "Data"
    sample_file = DATA_DIR / "000" / "Trajectory" / "20081023025304.plt"

    print("=== Test: Load with altitude ===")
    df_alt = load_plt(sample_file, keep_altitude=True)
    print(f"  Columns: {list(df_alt.columns)}")
    print(f"  Shape: {df_alt.shape}")
    print(f"  Altitude sample: {df_alt['altitude'].head(5).tolist()}")
    print(f"  Altitude NaN count: {df_alt['altitude'].isna().sum()}")

    # Test 2: Load without altitude (backward compatible)
    print("\n=== Test: Load without altitude ===")
    df_no_alt = load_plt(sample_file, keep_altitude=False)
    print(f"  Columns: {list(df_no_alt.columns)}")
    print(f"  Shape: {df_no_alt.shape}")

    # Test 3: Clean with altitude
    print("\n=== Test: Clean trajectory with altitude ===")
    cleaner = GPSCleaner(CleaningConfig())
    df_clean = cleaner.clean_trajectory(df_alt)
    print(f"  Before clean: {len(df_alt)} points")
    print(f"  After clean: {len(df_clean)} points")
    print(f"  Columns: {list(df_clean.columns)}")
    print(f"  Altitude NaN count: {df_clean['altitude'].isna().sum()}")

    # Test 4: Speed statistics
    print("\n=== Test: Speed statistics ===")
    if len(df_clean) > 1:
        from gps.data.cleaner import GPSCleaner as GC
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

    # Test 5: Split by gaps
    print("\n=== Test: Split by gaps ===")
    segments = cleaner.split_by_gaps(df_clean)
    print(f"  Segments after splitting by gaps: {len(segments)}")
    for i, seg in enumerate(segments[:3]):
        print(f"    Segment {i}: {len(seg)} points "
              f"({seg['timestamp'].min()} → {seg['timestamp'].max()})")


if __name__ == "__main__":
    main()
