"""
Monitoring and metrics collection.
"""
import time
from typing import Dict, List
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
import statistics


@dataclass
class LatencyStats:
    """Latency statistics."""
    count: int = 0
    total_ms: float = 0.0
    values: List[float] = field(default_factory=list)
    
    @property
    def mean_ms(self) -> float:
        return self.total_ms / self.count if self.count > 0 else 0
    
    @property
    def p50(self) -> float:
        return statistics.median(self.values) if self.values else 0
    
    @property
    def p95(self) -> float:
        if not self.values:
            return 0
        sorted_values = sorted(self.values)
        idx = int(len(sorted_values) * 0.95)
        return sorted_values[min(idx, len(sorted_values) - 1)]
    
    @property
    def p99(self) -> float:
        if not self.values:
            return 0
        sorted_values = sorted(self.values)
        idx = int(len(sorted_values) * 0.99)
        return sorted_values[min(idx, len(sorted_values) - 1)]


class MetricsCollector:
    """
    Collect and aggregate metrics.
    
    Tracks:
    - Request counts
    - Latency (p50, p95, p99)
    - Error rates
    - Classification counts
    """

    def __init__(self):
        self.requests: Dict[str, LatencyStats] = defaultdict(LatencyStats)
        self.errors: Dict[str, int] = defaultdict(int)
        self.classifications: Dict[str, int] = defaultdict(int)
        self.start_time = datetime.now()

    def record_request(
        self, 
        method: str, 
        path: str, 
        status: int, 
        duration: float
    ):
        """
        Record an API request.
        
        Args:
            method: HTTP method
            path: Request path
            status: HTTP status code
            duration: Request duration in seconds
        """
        key = f"{method}:{path}"
        latency_ms = duration * 1000
        
        self.requests[key].count += 1
        self.requests[key].total_ms += latency_ms
        self.requests[key].values.append(latency_ms)
        
        if status >= 400:
            self.errors[key] += 1

    def record_error(self, path: str):
        """Record an error."""
        self.errors[path] += 1

    def record_classification(self, location_type: str):
        """Record a classification by type."""
        self.classifications[location_type] += 1

    def get_latency_stats(self, endpoint: str) -> Dict:
        """Get latency statistics for an endpoint."""
        stats = self.requests.get(endpoint, LatencyStats())
        return {
            "count": stats.count,
            "mean_ms": stats.mean_ms,
            "p50_ms": stats.p50,
            "p95_ms": stats.p95,
            "p99_ms": stats.p99
        }

    def get_all_stats(self) -> Dict:
        """Get all collected statistics."""
        return {
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
            "requests": {
                endpoint: self.get_latency_stats(endpoint)
                for endpoint in self.requests.keys()
            },
            "errors": dict(self.errors),
            "classifications": dict(self.classifications),
            "total_requests": sum(s.count for s in self.requests.values()),
            "total_errors": sum(self.errors.values())
        }

    def get_metrics(self) -> str:
        """Get metrics in Prometheus format."""
        lines = ["# HELP gps_inference_requests_total Total requests"]
        lines.append("# TYPE gps_inference_requests_total counter")
        
        for endpoint, stats in self.requests.items():
            lines.append(f'gps_inference_requests_total{{endpoint="{endpoint}"}} {stats.count}')
        
        lines.append("\n# HELP gps_inference_latency_ms Request latency")
        lines.append("# TYPE gps_inference_latency_ms summary")
        
        for endpoint, stats in self.requests.items():
            lines.append(f'gps_inference_latency_ms{{endpoint="{endpoint}",quantile="0.5"}} {stats.p50}')
            lines.append(f'gps_inference_latency_ms{{endpoint="{endpoint}",quantile="0.95"}} {stats.p95}')
            lines.append(f'gps_inference_latency_ms{{endpoint="{endpoint}",quantile="0.99"}} {stats.p99}')
        
        return "\n".join(lines)
