"""
Model versioning utilities.
"""
from typing import Dict, Optional
from datetime import datetime
import json
from pathlib import Path


class ModelVersion:
    """Represents a single model version."""
    
    def __init__(
        self,
        version: str,
        model_type: str,
        config: Dict,
        metrics: Optional[Dict] = None,
        created_at: Optional[datetime] = None
    ):
        self.version = version
        self.model_type = model_type
        self.config = config
        self.metrics = metrics or {}
        self.created_at = created_at or datetime.now()
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "version": self.version,
            "model_type": self.model_type,
            "config": self.config,
            "metrics": self.metrics,
            "created_at": self.created_at.isoformat()
        }


def compare_versions(v1: ModelVersion, v2: ModelVersion) -> Dict:
    """
    Compare two model versions.
    
    Args:
        v1: First version
        v2: Second version
        
    Returns:
        Dictionary with comparison results
    """
    metric_diff = {}
    for key in set(v1.metrics.keys()) | set(v2.metrics.keys()):
        val1 = v1.metrics.get(key, 0)
        val2 = v2.metrics.get(key, 0)
        metric_diff[key] = {
            "v1": val1,
            "v2": val2,
            "diff": val2 - val1
        }
    
    return {
        "v1": v1.to_dict(),
        "v2": v2.to_dict(),
        "metric_differences": metric_diff
    }


def save_version_metadata(
    version: ModelVersion, 
    output_path: str
) -> None:
    """
    Save model version metadata to JSON file.
    
    Args:
        version: ModelVersion object
        output_path: Path to save JSON
    """
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(version.to_dict(), f, indent=2)


def load_version_metadata(filepath: str) -> ModelVersion:
    """
    Load model version from JSON file.
    
    Args:
        filepath: Path to JSON file
        
    Returns:
        ModelVersion object
    """
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    return ModelVersion(
        version=data["version"],
        model_type=data["model_type"],
        config=data["config"],
        metrics=data.get("metrics", {}),
        created_at=datetime.fromisoformat(data["created_at"])
    )


def get_next_version(current_version: str) -> str:
    """
    Get next version number.
    
    Args:
        current_version: Current version (e.g., 'v1')
        
    Returns:
        Next version (e.g., 'v2')
    """
    if current_version.startswith('v'):
        try:
            num = int(current_version[1:])
            return f"v{num + 1}"
        except ValueError:
            pass
    
    return current_version + "_next"
