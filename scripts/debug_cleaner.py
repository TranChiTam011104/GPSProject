"""Debug cleaner output."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np
from src.data.cleaner import GPSCleaner, CleaningConfig

DATA_DIR = PROJECT_ROOT / "data" / "Geolife Trajectories 1.3" / "Data" / "000" / "Trajectory"


def load_plt(filepath: Path) -> pd.DataFrame:
    df = pd.read_csv(
        filepath,
        skiprows=6,
        header=None,
        names=["lat", "lng", "altitude", "date", "time"],
    )
    df["timestamp"] = pd.to_datetime(df["date"] + " " + df["time"])
    return df[["lat", "lng", "timestamp"]]


df = load_plt(sorted(DATA_DIR.glob("*.plt"))[0])
print(f"Raw points: {len(df)}")

# Vectorised speed between consecutive points
lat1 = np.radians(df["lat"].to_numpy())
lat2 = np.radians(df["lat"].shift(1).to_numpy())
dlat = lat1 - lat2
dlng = np.radians(df["lng"].to_numpy()) - np.radians(df["lng"].shift(1).to_numpy())
a = np.sin(dlat / 2.0) ** 2 + np.cos(lat2) * np.cos(lat1) * np.sin(dlng / 2.0) ** 2
a = np.where(np.isnan(a), 0.0, a)
c = 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
distance_km = 6371.0088 * c
time_diff = df["timestamp"].diff().dt.total_seconds()
speed_kmh = (distance_km / time_diff) * 3600.0

print(f"\nSpeed stats:")
print(f"  min:    {np.nanmin(speed_kmh):.1f} km/h")
print(f"  max:    {np.nanmax(speed_kmh):.1f} km/h")
print(f"  median: {np.nanmedian(speed_kmh):.1f} km/h")
print(f"  p99:    {np.nanpercentile(speed_kmh, 99):.1f} km/h")
print(f"  > 300 km/h: {(speed_kmh > 300).sum()} points")

print(f"\nDistance jump stats:")
print(f"  max:    {np.nanmax(distance_km):.4f} km")
print(f"  median: {np.nanmedian(distance_km):.4f} km")
print(f"  p99:    {np.nanpercentile(distance_km, 99):.4f} km")
print(f"  > 50 km: {(distance_km > 50).sum()} points")
print(f"  > 10 km: {(distance_km > 10).sum()} points")
