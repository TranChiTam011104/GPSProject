"""
Deployment strategies implementation.

Supports:
- Shadow: Run new model alongside old, log results only
- Canary: Route small percentage of traffic to new model
- Blue-Green: Full environment switch
"""
from enum import Enum
from typing import Callable, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
import random
import logging


logger = logging.getLogger(__name__)


class DeploymentStrategy(Enum):
    """Available deployment strategies."""
    SHADOW = "shadow"
    CANARY = "canary"
    BLUE_GREEN = "blue_green"
    ROLLING = "rolling"


@dataclass
class DeploymentConfig:
    """Configuration for deployment strategy."""
    strategy: DeploymentStrategy
    canary_percentage: float = 0.1  # 10% traffic to new model
    shadow_enabled: bool = True
    health_check_interval: int = 60  # seconds


@dataclass
class DeploymentState:
    """Current state of deployment."""
    active_model: str
    standby_model: str
    strategy: DeploymentStrategy
    started_at: datetime
    traffic_split: Dict[str, float]
    is_healthy: bool = True


class DeployStrategyManager:
    """
    Manager for deployment strategies.
    
    Handles traffic routing between model versions.
    """

    def __init__(self, config: DeploymentConfig):
        self.config = config
        self.state = None

    def initialize(
        self, 
        active_model: str = "v1", 
        standby_model: str = "v2"
    ):
        """Initialize deployment state."""
        traffic_split = {
            active_model: 1.0,
            standby_model: 0.0
        }
        
        if self.config.strategy == DeploymentStrategy.CANARY:
            traffic_split = {
                active_model: 1 - self.config.canary_percentage,
                standby_model: self.config.canary_percentage
            }
        elif self.config.strategy == DeploymentStrategy.SHADOW:
            traffic_split = {
                active_model: 1.0,
                standby_model: 1.0  # Both receive all traffic
            }
        
        self.state = DeploymentState(
            active_model=active_model,
            standby_model=standby_model,
            strategy=self.config.strategy,
            started_at=datetime.now(),
            traffic_split=traffic_split
        )
        
        logger.info(f"Initialized {self.config.strategy.value} deployment: {traffic_split}")

    def route_request(self) -> str:
        """
        Route a request to appropriate model.
        
        Returns:
            Model version to handle the request
        """
        if self.state is None:
            raise RuntimeError("Deployment not initialized")
        
        rand = random.random()
        cumulative = 0.0
        
        for model, ratio in self.state.traffic_split.items():
            cumulative += ratio
            if rand < cumulative:
                return model
        
        return self.state.active_model

    def process_with_shadow(
        self, 
        request_data: dict,
        primary_fn: Callable,
        shadow_fn: Callable
    ) -> dict:
        """
        Process request with shadow model.
        
        Args:
            request_data: Request payload
            primary_fn: Primary model prediction function
            shadow_fn: Shadow model prediction function
            
        Returns:
            Primary model result
        """
        # Process with primary model
        primary_result = primary_fn(request_data)
        
        # Process with shadow model (log only)
        if self.config.shadow_enabled:
            try:
                shadow_result = shadow_fn(request_data)
                self._log_shadow_comparison(primary_result, shadow_result)
            except Exception as e:
                logger.warning(f"Shadow model error: {e}")
        
        return primary_result

    def _log_shadow_comparison(
        self, 
        primary: dict, 
        shadow: dict
    ):
        """Log comparison between primary and shadow results."""
        logger.info(
            f"Shadow comparison: primary={primary.get('result')}, "
            f"shadow={shadow.get('result')}"
        )

    def promote_model(self):
        """
        Promote standby model to active (for Blue-Green or Canary).
        """
        if self.state is None:
            raise RuntimeError("Deployment not initialized")
        
        old_active = self.state.active_model
        self.state.active_model = self.state.standby_model
        self.state.standby_model = old_active
        self.state.traffic_split = {
            self.state.active_model: 1.0,
            self.state.standby_model: 0.0
        }
        
        logger.info(f"Promoted {self.state.active_model} to active")

    def update_canary_percentage(self, percentage: float):
        """
        Update canary traffic percentage.
        
        Args:
            percentage: New percentage for canary (0.0 to 1.0)
        """
        if self.config.strategy != DeploymentStrategy.CANARY:
            logger.warning("Canary percentage update ignored - not in canary mode")
            return
        
        self.config.canary_percentage = percentage
        self.state.traffic_split = {
            self.state.active_model: 1 - percentage,
            self.state.standby_model: percentage
        }
        
        logger.info(f"Updated canary to {percentage * 100}%")

    def rollback(self):
        """Rollback to previous active model."""
        if self.state is None:
            raise RuntimeError("Deployment not initialized")
        
        self.state.active_model, self.state.standby_model = (
            self.state.standby_model, 
            self.state.active_model
        )
        self.state.traffic_split = {
            self.state.active_model: 1.0,
            self.state.standby_model: 0.0
        }
        
        logger.warning(f"Rolled back to {self.state.active_model}")

    def get_state(self) -> DeploymentState:
        """Get current deployment state."""
        return self.state


def create_strategy_manager(
    strategy: str,
    **kwargs
) -> DeployStrategyManager:
    """
    Factory function to create strategy manager.
    
    Args:
        strategy: Strategy name ('shadow', 'canary', 'blue_green')
        **kwargs: Additional configuration
        
    Returns:
        DeployStrategyManager instance
    """
    strategy_enum = DeploymentStrategy(strategy.lower())
    
    config = DeploymentConfig(
        strategy=strategy_enum,
        canary_percentage=kwargs.get("canary_percentage", 0.1),
        shadow_enabled=kwargs.get("shadow_enabled", True)
    )
    
    return DeployStrategyManager(config)
