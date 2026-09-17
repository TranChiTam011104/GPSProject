"""Detailed inspection."""
import pandas as pd

p = r"d:\Hoc_voi_cha_hanh\AIInAction\VSF_Intern\GPSProject\data\Geolife Trajectories 1.3\Data\000\Trajectory\20081023025304.plt"
df = pd.read_csv(
    p, skiprows=6, header=None,
    names=["lat", "lng", "alt", "date", "time"],
)

print(f"dtypes:\n{df.dtypes}")
print(f"\ndf.shape: {df.shape}")
print(f"df.columns: {list(df.columns)}")

# Check the actual raw row 100
with open(p) as f:
    lines = f.readlines()

print(f"\nLine 0: {lines[0].strip()}")
print(f"Line 6: {lines[6].strip()}")  # First data
print(f"Line 100: {lines[100].strip()}")
print(f"Line 500: {lines[500].strip()}")
print(f"Line 905: {lines[905].strip()}")
print(f"Line {len(lines)-1}: {lines[-1].strip()}")

# Now read raw with names=None and inspect
print("\n--- Raw read ---")
df2 = pd.read_csv(p, skiprows=6, header=None)
print(f"Columns: {df2.columns.tolist()}")
print(df2.head(3))
print()
print(df2.tail(3))
