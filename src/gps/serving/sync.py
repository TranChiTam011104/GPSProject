"""
Synchronous model serving (request-response pattern).
"""
from typing import Dict, List
from gps.models.base import BaseClassifier, ClassificationResult
import time
import logging


logger = logging.getLogger(__name__)


class SyncServing:
    """
    Synchronous serving for real-time classification.
    
    Pattern: Request → Process → Response
    
    Best for:
    - Real-time classification
    - Low latency requirements
    - Interactive applications
    """

    def __init__(self, classifier: BaseClassifier):
        self.classifier = classifier

    def serve(
        self, 
        user_id: str, 
        stay_points: List[dict]
    ) -> Dict:
        """
        Serve a classification request synchronously.
        
        Args:
            user_id: User identifier
            stay_points: List of stay-point dictionaries
            
        Returns:
            Classification result dictionary
        """
        start_time = time.time()
        
        try:
            result = self.classifier.predict(stay_points)
            
            duration = time.time() - start_time
            
            logger.info(
                f"Sync serving completed for user {user_id} "
                f"in {duration*1000:.2f}ms"
            )
            
            return {
                "success": True,
                "result": result.to_dict(),
                "latency_ms": duration * 1000
            }
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Sync serving failed: {e}", exc_info=True)
            
            return {
                "success": False,
                "error": str(e),
                "latency_ms": duration * 1000
            }

    def serve_batch(
        self, 
        requests: List[Dict[str, any]]
    ) -> List[Dict]:
        """
        Serve multiple classification requests.
        
        Args:
            requests: List of (user_id, stay_points) tuples
            
        Returns:
            List of results
        """
        results = []
        
        for req in requests:
            user_id = req.get("user_id")
            stay_points = req.get("stay_points", [])
            result = self.serve(user_id, stay_points)
            results.append(result)
        
        return results


def create_sync_server(classifier: BaseClassifier) -> SyncServing:
    """
    Factory function to create sync server.
    
    Args:
        classifier: Model classifier
        
    Returns:
        SyncServing instance
    """
    return SyncServing(classifier)
