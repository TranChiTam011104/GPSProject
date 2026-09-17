# Drift Detection Guide

## Overview

Drift detection monitors changes in model behavior over time. Since GeoLife is static data (2007-2012), we simulate drift by replaying trajectories in time order.

## Types of Drift

### 1. Location Drift
Distribution of classified locations changes over time.

**Detection Method**: Population Stability Index (PSI)

### 2. Trajectory Drift
Movement patterns shift (e.g., new commute routes).

**Detection Method**: Distribution comparison on trajectory features

### 3. Classification Drift
Ratio of home/office/POI classifications changes.

**Detection Method**: Chi-square test on classification counts

## Implementation

```python
from src.monitoring.drift import DriftDetector

detector = DriftDetector(
    window_size=1000,
    threshold=0.2,
    metrics=["location_distribution", "classification_ratio"]
)

# Establish baseline
for prediction in baseline_predictions:
    detector.record_prediction(
        lat=prediction["lat"],
        lng=prediction["lng"],
        location_type=prediction["type"]
    )
detector.establish_baseline()

# Monitor live predictions
for prediction in live_predictions:
    detector.record_prediction(
        lat=prediction["lat"],
        lng=prediction["lng"],
        location_type=prediction["type"]
    )

# Check for drift
reports = detector.check_all_drift()
for report in reports:
    if report.drift_detected:
        logger.warning(f"Drift detected: {report.metric_name}")
```

## Simulating Drift on GeoLife

Since GeoLife is historical data, simulate drift by:

1. Sort trajectories chronologically
2. Process in time order as if streaming
3. Compare distribution between time windows

```python
def simulate_drift(trajectories):
    # Sort by time
    sorted_traj = sorted(trajectories, key=lambda x: x["timestamp"])
    
    detector = DriftDetector()
    
    # Process in batches (e.g., per day/week)
    batch_size = 1000
    for i in range(0, len(sorted_traj), batch_size):
        batch = sorted_traj[i:i+batch_size]
        
        for traj in batch:
            detector.record_prediction(
                lat=traj["lat"],
                lng=traj["lng"],
                location_type=traj["type"]
            )
        
        # Check for drift
        reports = detector.check_all_drift()
        if any(r.drift_detected for r in reports):
            print(f"Drift detected at batch {i//batch_size}")
```

## PSI Thresholds

| PSI Value | Interpretation |
|-----------|---------------|
| < 0.1 | No significant change |
| 0.1 - 0.2 | Moderate change (investigate) |
| > 0.2 | Significant change (action required) |

## Alerts

When drift is detected:

1. Log warning with details
2. Send to CloudWatch metric
3. Optionally trigger model retraining
4. Notify via SNS topic

## Dashboard Metrics

Track in monitoring dashboard:
- PSI score per metric
- Drift alert count per day
- Time since last drift detected
- Distribution comparison charts
