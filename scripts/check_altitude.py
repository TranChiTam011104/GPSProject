"""Check altitude distribution in GeoLife data."""
from pathlib import Path
import pandas as pd

data_dir = Path(r"d:\Hoc_voi_cha_hanh\AIInAction\VSF_Intern\GPSProject\data\Geolife Trajectories 1.3\Data")

# Check first 5 users
total_points = 0
total_alt_invalid = 0
samples = []

for user_folder in sorted(data_dir.iterdir())[:5]:
    if not user_folder.name.startswith("0"):
        continue
    traj_dir = user_folder / "Trajectory"
    if not traj_dir.exists():
        continue
    
    for plt_file in list(traj_dir.glob("*.plt"))[:3]:  # First 3 files per user
        df = pd.read_csv(
            plt_file, skiprows=6, header=None,
            names=["lat", "lng", "unused", "altitude", "date_num", "date", "time"],
        )
        total_points += len(df)
        alt_invalid = (df["altitude"] == -777).sum()
        total_alt_invalid += alt_invalid
        
        # Sample altitude values
        if len(samples) < 10:
            samples.extend(df["altitude"].head(10).tolist())

print(f"Total points checked: {total_points}")
print(f"Altitude = -777 count: {total_alt_invalid}")
print(f"Percentage invalid: {total_alt_invalid/total_points*100:.1f}%")
print(f"\nSample altitude values: {samples}")
