"""
Batch processing for large-scale classification.
"""
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging


logger = logging.getLogger(__name__)


@dataclass
class BatchJob:
    """Represents a batch classification job."""
    job_id: str
    user_ids: List[str]
    status: str = "pending"  # pending, processing, completed, failed
    created_at: datetime = None
    completed_at: Optional[datetime] = None
    results: List[Dict] = field(default_factory=list)
    errors: List[Dict] = field(default_factory=list)
    total_users: int = 0
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        self.total_users = len(self.user_ids)


class BatchProcessor:
    """
    Process classification requests in batches.
    
    Optimized for processing many users efficiently.
    """

    def __init__(self, classifier, batch_size: int = 100):
        self.classifier = classifier
        self.batch_size = batch_size
        self.jobs: Dict[str, BatchJob] = {}

    def submit_batch(
        self, 
        user_data: List[Dict[str, any]]
    ) -> str:
        """
        Submit a batch of users for classification.
        
        Args:
            user_data: List of dicts with 'user_id' and 'stay_points'
            
        Returns:
            Batch job ID
        """
        import uuid
        
        job_id = str(uuid.uuid4())
        user_ids = [u["user_id"] for u in user_data]
        
        job = BatchJob(
            job_id=job_id,
            user_ids=user_ids
        )
        
        self.jobs[job_id] = job
        
        logger.info(f"Submitted batch {job_id} with {len(user_ids)} users")
        
        return job_id

    def process_batch(
        self, 
        job_id: str, 
        user_data: List[Dict[str, any]]
    ) -> Dict:
        """
        Process a batch job.
        
        Args:
            job_id: Job identifier
            user_data: List of user data with 'user_id' and 'stay_points'
            
        Returns:
            Processing results
        """
        job = self.jobs.get(job_id)
        
        if job is None:
            return {"success": False, "error": "Job not found"}
        
        job.status = "processing"
        
        for i in range(0, len(user_data), self.batch_size):
            batch = user_data[i:i + self.batch_size]
            
            for user_data_item in batch:
                try:
                    user_id = user_data_item["user_id"]
                    stay_points = user_data_item["stay_points"]
                    
                    result = self.classifier.predict(stay_points)
                    job.results.append({
                        "user_id": user_id,
                        "success": True,
                        "result": result.to_dict()
                    })
                except Exception as e:
                    job.errors.append({
                        "user_id": user_data_item.get("user_id", "unknown"),
                        "error": str(e)
                    })
                    logger.error(f"Error processing user: {e}")
        
        job.status = "completed"
        job.completed_at = datetime.now()
        
        successful = len(job.results)
        failed = len(job.errors)
        
        logger.info(
            f"Batch {job_id} completed: "
            f"{successful} successful, {failed} failed"
        )
        
        return {
            "job_id": job_id,
            "successful": successful,
            "failed": failed,
            "total": len(user_data),
            "results": job.results,
            "errors": job.errors
        }

    def get_job_status(self, job_id: str) -> Optional[BatchJob]:
        """Get batch job status."""
        return self.jobs.get(job_id)


def create_batch_processor(
    classifier, 
    batch_size: int = 100
) -> BatchProcessor:
    """
    Factory function to create batch processor.
    
    Args:
        classifier: Model classifier
        batch_size: Number of users per batch
        
    Returns:
        BatchProcessor instance
    """
    return BatchProcessor(classifier, batch_size)
