"""
Structured logging for API requests and model predictions.
"""
import logging
import json
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass, asdict
import uuid


@dataclass
class RequestLog:
    """Structured request log entry."""
    request_id: str
    method: str
    path: str
    status: int
    duration_ms: float
    user_id: Optional[str] = None
    model_version: Optional[str] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class PredictionLog:
    """Structured prediction log entry."""
    request_id: str
    user_id: str
    num_stay_points: int
    home_location: Optional[Dict]
    office_location: Optional[Dict]
    num_pois: int
    model_version: str
    latency_ms: float
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return asdict(self)


class RequestLogger:
    """
    Structured logger for API requests and predictions.
    """

    def __init__(self, logger_name: str = "gps_inference"):
        self.logger = logging.getLogger(logger_name)
        
        # Configure JSON logging
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def log_request(self, **kwargs):
        """
        Log an API request.
        
        Args:
            **kwargs: RequestLog fields
        """
        if "request_id" not in kwargs:
            kwargs["request_id"] = str(uuid.uuid4())
        
        log_entry = RequestLog(**kwargs)
        self.logger.info(json.dumps(log_entry.to_dict()))

    def log_prediction(self, **kwargs):
        """
        Log a prediction.
        
        Args:
            **kwargs: PredictionLog fields
        """
        if "request_id" not in kwargs:
            kwargs["request_id"] = str(uuid.uuid4())
        
        log_entry = PredictionLog(**kwargs)
        self.logger.info(json.dumps(log_entry.to_dict()))

    def log_error(self, request_id: str, error: str, **kwargs):
        """
        Log an error.
        
        Args:
            request_id: Request identifier
            error: Error message
            **kwargs: Additional fields
        """
        log_data = {
            "request_id": request_id,
            "event": "error",
            "error": error,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        self.logger.error(json.dumps(log_data))


# Global logger instance
_logger: Optional[RequestLogger] = None


def get_logger() -> RequestLogger:
    """Get global logger instance."""
    global _logger
    if _logger is None:
        _logger = RequestLogger()
    return _logger
