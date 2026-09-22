"""
Quick test for stay-point detection and home/office classification.
Uses sample data for fast testing.
"""

import pandas as pd
import numpy as np
import time
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# After the src/ → src/gps/ refactor, the legacy names map onto:
#   src.models.stay_point_detection       → gps.features.stay_point
#   src.models.home_office_classifier     → (replaced by gps.models.heuristic)
# This script is kept here for reference but its API surface has shifted;
# re-target it once Checkpoint 2 introduces DBSCAN (v2) and a richer
# user-profile dataclass.


def test_user(user_id: str, sample_size: int = None):
    """Test với 1 user."""
    print(f"\n{'='*60}")
    print(f"Testing User {user_id}")
    print('='*60)
    
    # Load data - try both relative paths
    possible_paths = [
        f"data/processed_v1/user_{user_id}.parquet",
        os.path.join(os.path.dirname(__file__), "..", "data", "processed_v1", f"user_{user_id}.parquet"),
        f"../data/processed_v1/user_{user_id}.parquet",
    ]
    
    data_path = None
    for p in possible_paths:
        if os.path.exists(p):
            data_path = p
            break
    
    if not data_path:
        print(f"File not found. Tried: {possible_paths}")
        return
    
    print(f"Loading data from: {data_path}")
    df = pd.read_parquet(data_path)
    print(f"Loaded {len(df)} GPS points")
    
    if sample_size and len(df) > sample_size:
        df = df.head(sample_size)
        print(f"Using sample of {len(df)} points")
    
    # Detect stay-points
    print(f"\nDetecting stay-points...")
    start = time.time()
    
    thresholds = StayPointThresholds(
        time_threshold_minutes=30.0,  # 30 phút
        distance_threshold_meters=200.0  # 200m
    )
    
    sps = detect_stay_points(df, thresholds=thresholds)
    elapsed = time.time() - start
    
    print(f"Detected {len(sps)} stay-points in {elapsed:.2f}s")
    
    if sps:
        sp_df = stay_points_to_dataframe(sps)
        print(f"\nStay-points summary:")
        print(f"  Total duration: {sp_df['duration_minutes'].sum():.1f} minutes")
        print(f"  Avg duration: {sp_df['duration_minutes'].mean():.1f} minutes")
        print(f"  Max duration: {sp_df['duration_minutes'].max():.1f} minutes")
        
        # Top 5 longest stay-points
        print(f"\nTop 5 longest stay-points:")
        top5 = sp_df.nlargest(5, 'duration_minutes')
        for _, row in top5.iterrows():
            print(f"  - {row['start_time']} -> {row['end_time']}")
            print(f"    Duration: {row['duration_minutes']:.1f} min, Points: {row['n_points']}")
            print(f"    Location: ({row['lat']:.6f}, {row['lon']:.6f})")
        
        # Classify home/office
        print(f"\nClassifying locations...")
        profile = classify_user_locations(sps, user_id)
        
        print(f"\nUser {profile.user_id} Profile:")
        print(f"  Analysis period: {profile.analysis_start} to {profile.analysis_end}")
        print(f"  Total clusters: {len(profile.all_clusters)}")
        
        if profile.home_location:
            h = profile.home_location
            print(f"\n  HOME: ({h.lat:.6f}, {h.lon:.6f})")
            print(f"    Confidence: {h.home_score:.2f}")
            print(f"    Visits: {h.visit_count}")
            print(f"    Total duration: {h.total_duration_minutes/60:.1f} hours")
        
        if profile.office_location:
            o = profile.office_location
            print(f"\n  OFFICE: ({o.lat:.6f}, {o.lon:.6f})")
            print(f"    Confidence: {o.office_score:.2f}")
            print(f"    Visits: {o.visit_count}")
            print(f"    Total duration: {o.total_duration_minutes/60:.1f} hours")
        
        # Print JSON
        print(f"\nJSON output:")
        import json
        print(json.dumps(profile_to_dict(profile), indent=2))
    else:
        print("No stay-points detected!")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test stay-point detection")
    parser.add_argument("--user", "-u", default="010", help="User ID")
    parser.add_argument("--sample", "-s", type=int, default=50000, help="Sample size")
    
    args = parser.parse_args()
    
    test_user(args.user, args.sample)
