"""
MLflow model registry integration.
"""
from typing import Optional, List, Dict
from dataclasses import dataclass
from datetime import datetime
import json
import logging


logger = logging.getLogger(__name__)


@dataclass
class ModelVersion:
    """Represents a model version in the registry."""
    name: str
    version: str
    stage: str  # staging, production, archived
    created_at: datetime
    metrics: Dict
    params: Dict
    artifacts_uri: Optional[str] = None


class ModelRegistry:
    """
    Simple model registry for versioning and staging.
    
    In production, this would use MLflow Model Registry.
    This provides a simpler interface for development.
    """

    def __init__(self, registry_path: str = "./models"):
        self.registry_path = registry_path
        self.models: Dict[str, List[ModelVersion]] = {}

    def register_model(
        self,
        name: str,
        version: str,
        artifacts_path: str,
        metrics: Dict = None,
        params: Dict = None
    ) -> ModelVersion:
        """
        Register a new model version.
        
        Args:
            name: Model name
            version: Version string (e.g., 'v1', 'v2')
            artifacts_path: Path to model artifacts
            metrics: Model metrics
            params: Model parameters
            
        Returns:
            ModelVersion object
        """
        model_version = ModelVersion(
            name=name,
            version=version,
            stage="staging",
            created_at=datetime.now(),
            metrics=metrics or {},
            params=params or {},
            artifacts_uri=artifacts_path
        )
        
        if name not in self.models:
            self.models[name] = []
        
        self.models[name].append(model_version)
        
        logger.info(f"Registered model {name}:{version}")
        
        return model_version

    def get_model(
        self, 
        name: str, 
        version: Optional[str] = None,
        stage: Optional[str] = None
    ) -> Optional[ModelVersion]:
        """
        Get a model by name, version, or stage.
        
        Args:
            name: Model name
            version: Specific version (optional)
            stage: Stage name (staging, production, archived)
            
        Returns:
            ModelVersion or None
        """
        if name not in self.models:
            return None
        
        versions = self.models[name]
        
        if version:
            for v in versions:
                if v.version == version:
                    return v
        elif stage:
            for v in versions:
                if v.stage == stage:
                    return v
        else:
            # Return latest
            return versions[-1] if versions else None
        
        return None

    def list_models(self) -> List[str]:
        """List all registered model names."""
        return list(self.models.keys())

    def list_versions(self, name: str) -> List[ModelVersion]:
        """List all versions of a model."""
        return self.models.get(name, [])

    def transition_stage(
        self, 
        name: str, 
        version: str, 
        new_stage: str
    ):
        """
        Transition model to a new stage.
        
        Args:
            name: Model name
            version: Model version
            new_stage: New stage (staging, production, archived)
        """
        model = self.get_model(name, version=version)
        
        if model:
            old_stage = model.stage
            model.stage = new_stage
            logger.info(f"Transitioned {name}:{version} from {old_stage} to {new_stage}")
        else:
            logger.warning(f"Model {name}:{version} not found")

    def archive_model(self, name: str, version: str):
        """Archive a model version."""
        self.transition_stage(name, version, "archived")

    def migrate_version(self, from_version: str, to_version: str):
        """
        Migrate traffic from one version to another.
        
        Args:
            from_version: Source version
            to_version: Target version
        """
        # Archive old version
        self.archive_version(from_version)
        
        # Transition new version to production
        self.transition_stage(self.models[0].name, to_version, "production")
        
        logger.info(f"Migrated from {from_version} to {to_version}")

    def export_metadata(self, filepath: str):
        """Export registry metadata to JSON."""
        data = {
            "exported_at": datetime.now().isoformat(),
            "models": {}
        }
        
        for name, versions in self.models.items():
            data["models"][name] = [
                {
                    "version": v.version,
                    "stage": v.stage,
                    "created_at": v.created_at.isoformat(),
                    "metrics": v.metrics,
                    "params": v.params
                }
                for v in versions
            ]
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Exported registry metadata to {filepath}")


# Global registry instance
_registry: Optional[ModelRegistry] = None


def get_registry() -> ModelRegistry:
    """Get global model registry."""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
