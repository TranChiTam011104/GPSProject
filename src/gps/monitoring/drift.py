"""
Drift detection for monitoring model behavior changes.
"""
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import deque
import logging


logger = logging.getLogger(__name__)


@dataclass
class DriftReport:
    """Report of detected drift."""
    metric_name: str
    drift_detected: bool
    current_value: float
    baseline_value: float
    change_percentage: float
    timestamp: datetime
    severity: str  # none, low, medium, high


class DriftDetector:
    """
    Detect distribution drift in model predictions.
    
    Monitors:
    - Location distribution
    - Trajectory patterns
    - Classification ratios
    """

    def __init__(
        self,
        window_size: int = 1000,
        threshold: float = 0.2,
        metrics: List[str] = None
    ):
        self.window_size = window_size
        self.threshold = threshold
        self.metrics = metrics or ["location_distribution", "classification_ratio"]
        
        # Store historical data
        self.baseline: Dict[str, np.ndarray] = {}
        self.current_window: Dict[str, deque] = {
            m: deque(maxlen=window_size) for m in self.metrics
        }
        
        # Drift reports
        self.reports: List[DriftReport] = []

    def record(self, metric_name: str, value: float):
        """
        Record a metric value.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
        """
        if metric_name not in self.metrics:
            return
        
        self.current_window[metric_name].append(value)

    def record_prediction(
        self, 
        lat: float, 
        lng: float, 
        location_type: str
    ):
        """
        Record a prediction for drift monitoring.
        
        Args:
            lat: Latitude
            lng: Longitude
            location_type: Predicted location type
        """
        # Record location (could use geohash for distribution)
        self.record("location_distribution", lat + lng)
        
        # Record classification type as numeric
        type_map = {"home": 0, "office": 1, "poi": 2, "unknown": 3}
        self.record("classification_ratio", type_map.get(location_type, 3))

    def establish_baseline(self):
        """Establish baseline from current window."""
        for metric_name in self.metrics:
            values = list(self.current_window[metric_name])
            if len(values) >= self.window_size // 2:
                self.baseline[metric_name] = np.array(values)
                logger.info(f"Established baseline for {metric_name}: {len(values)} samples")

    def check_drift(self, metric_name: str) -> Optional[DriftReport]:
        """
        Check for drift in a specific metric.
        
        Args:
            metric_name: Name of the metric
            
        Returns:
            DriftReport or None if not enough data
        """
        if metric_name not in self.baseline:
            return None
        
        baseline = self.baseline[metric_name]
        current = np.array(list(self.current_window[metric_name]))
        
        if len(current) < self.window_size // 4:
            return None
        
        # Calculate statistics
        baseline_mean = np.mean(baseline)
        current_mean = np.mean(current)
        
        # Calculate change
        if baseline_mean != 0:
            change_pct = abs(current_mean - baseline_mean) / abs(baseline_mean)
        else:
            change_pct = abs(current_mean) if current_mean != 0 else 0
        
        # Determine severity
        if change_pct < self.threshold * 0.5:
            severity = "none"
        elif change_pct < self.threshold:
            severity = "low"
        elif change_pct < self.threshold * 2:
            severity = "medium"
        else:
            severity = "high"
        
        drift_detected = change_pct >= self.threshold
        
        report = DriftReport(
            metric_name=metric_name,
            drift_detected=drift_detected,
            current_value=current_mean,
            baseline_value=baseline_mean,
            change_percentage=change_pct * 100,
            timestamp=datetime.now(),
            severity=severity
        )
        
        if drift_detected:
            logger.warning(
                f"Drift detected in {metric_name}: "
                f"baseline={baseline_mean:.4f}, current={current_mean:.4f}, "
                f"change={change_pct*100:.1f}%"
            )
        
        self.reports.append(report)
        
        return report

    def check_all_drift(self) -> List[DriftReport]:
        """Check drift for all metrics."""
        reports = []
        for metric_name in self.metrics:
            report = self.check_drift(metric_name)
            if report:
                reports.append(report)
        return reports

    def get_recent_alerts(self, hours: int = 24) -> List[DriftReport]:
        """Get drift alerts from the last N hours."""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [
            r for r in self.reports 
            if r.timestamp >= cutoff and r.drift_detected
        ]


def calculate_psi(
    expected: np.ndarray, 
    actual: np.ndarray, 
    buckets: int = 10
) -> float:
    """
    Calculate Population Stability Index (PSI).
    
    Args:
        expected: Expected distribution
        actual: Actual distribution
        buckets: Number of buckets for comparison
        
    Returns:
        PSI value (lower = more stable)
    """
    # Create buckets
    breakpoints = np.linspace(0, 100, buckets + 1)
    
    expected_pct = np.histogram(expected, bins=breakpoints)[0] / len(expected)
    actual_pct = np.histogram(actual, bins=breakpoints)[0] / len(actual)
    
    # Avoid division by zero
    expected_pct = np.where(expected_pct == 0, 0.0001, expected_pct)
    actual_pct = np.where(actual_pct == 0, 0.0001, actual_pct)
    
    # Calculate PSI
    psi = np.sum(
        (actual_pct - expected_pct) * np.log(actual_pct / expected_pct)
    )
    
    return float(psi)
