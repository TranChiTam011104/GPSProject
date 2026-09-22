"""
API version routing for handling multiple API versions.
"""
from fastapi import APIRouter, Depends
from typing import Dict, Callable
import logging


logger = logging.getLogger(__name__)


class VersionedAPIRouter:
    """
    Router that handles multiple API versions.
    
    Allows defining routes for v1, v2, etc. and routing
    requests based on URL prefix.
    """

    def __init__(self):
        self.routers: Dict[str, APIRouter] = {}
        self.handlers: Dict[str, Dict[str, Callable]] = {}

    def add_route(
        self,
        version: str,
        path: str,
        handler: Callable,
        methods: list = ["POST"]
    ):
        """
        Add a route for a specific API version.
        
        Args:
            version: API version (e.g., 'v1', 'v2')
            path: Route path
            handler: Handler function
            methods: HTTP methods
        """
        if version not in self.routers:
            self.routers[version] = APIRouter(prefix=f"/{version}")
        
        self.routers[version].add_api_route(
            path,
            handler,
            methods=methods
        )
        
        if version not in self.handlers:
            self.handlers[version] = {}
        self.handlers[version][path] = handler
        
        logger.info(f"Added {version}{path}")

    def get_routers(self) -> Dict[str, APIRouter]:
        """Get all versioned routers."""
        return self.routers

    def get_latest_version(self) -> str:
        """Get the latest version available."""
        versions = sorted(self.routers.keys())
        return versions[-1] if versions else "v1"


# Global versioned router
versioned_router = VersionedAPIRouter()


def get_versioned_router() -> VersionedAPIRouter:
    """Get the global versioned router."""
    return versioned_router


class APIVersionManager:
    """
    Manages API version deprecation and migration.
    """

    def __init__(self):
        self.deprecated_versions: Dict[str, str] = {}
        self.supported_versions = ["v1"]

    def deprecate_version(self, version: str, sunset_date: str):
        """
        Mark a version as deprecated.
        
        Args:
            version: API version
            sunset_date: Date when version will be removed
        """
        self.deprecated_versions[version] = sunset_date
        logger.warning(
            f"API version {version} deprecated, "
            f"will be removed on {sunset_date}"
        )

    def is_deprecated(self, version: str) -> bool:
        """Check if a version is deprecated."""
        return version in self.deprecated_versions

    def get_deprecation_info(self, version: str) -> str:
        """Get deprecation info for a version."""
        if version in self.deprecated_versions:
            return f"Deprecated, will be removed on {self.deprecated_versions[version]}"
        return "Active"
