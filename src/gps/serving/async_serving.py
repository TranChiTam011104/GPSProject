"""
Asynchronous model serving using SQS queue.
"""
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
import time
import logging
import uuid


logger = logging.getLogger(__name__)


@dataclass
class AsyncJob:
    """Represents an async classification job."""
    job_id: str
    user_id: str
    status: str  # pending, processing, completed, failed
    created_at: datetime
    completed_at: Optional[datetime] = None
    result: Optional[Dict] = None
    error: Optional[str] = None


class AsyncServing:
    """
    Asynchronous serving for batch classification.
    
    Pattern: Request → Queue → Worker → Store Result → Client Poll/Callback
    
    Best for:
    - Batch processing large number of users
    - High throughput scenarios
    - Non-interactive applications
    """

    def __init__(
        self, 
        classifier,
        sqs_queue_url: Optional[str] = None,
        result_store: Optional[Callable] = None
    ):
        self.classifier = classifier
        self.sqs_queue_url = sqs_queue_url
        self.result_store = result_store
        self.jobs: Dict[str, AsyncJob] = {}

    def submit_job(
        self, 
        user_id: str, 
        stay_points: List[dict]
    ) -> str:
        """
        Submit a classification job to the queue.
        
        Args:
            user_id: User identifier
            stay_points: List of stay-point dictionaries
            
        Returns:
            Job ID for tracking
        """
        job_id = str(uuid.uuid4())
        
        job = AsyncJob(
            job_id=job_id,
            user_id=user_id,
            status="pending",
            created_at=datetime.now()
        )
        
        self.jobs[job_id] = job
        
        # In production, send to SQS here
        if self.sqs_queue_url:
            self._send_to_sqs(job_id, user_id, stay_points)
        
        logger.info(f"Submitted job {job_id} for user {user_id}")
        
        return job_id

    def get_job_status(self, job_id: str) -> Optional[AsyncJob]:
        """
        Get status of a job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            AsyncJob object or None if not found
        """
        return self.jobs.get(job_id)

    def get_job_result(self, job_id: str) -> Optional[Dict]:
        """
        Get result of a completed job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Result dictionary or None if not ready
        """
        job = self.jobs.get(job_id)
        
        if job is None:
            return None
        
        if job.status == "completed":
            return job.result
        
        return None

    def process_job(self, job_id: str) -> Dict:
        """
        Process a pending job (called by worker).
        
        Args:
            job_id: Job identifier
            
        Returns:
            Processing result
        """
        job = self.jobs.get(job_id)
        
        if job is None:
            return {"success": False, "error": "Job not found"}
        
        job.status = "processing"
        start_time = time.time()
        
        try:
            # Get stay_points from somewhere (SQS, DB, etc.)
            stay_points = self._get_job_data(job_id)
            
            # Run classification
            result = self.classifier.predict(stay_points)
            
            duration = time.time() - start_time
            
            job.status = "completed"
            job.result = result.to_dict()
            job.completed_at = datetime.now()
            
            logger.info(
                f"Job {job_id} completed in {duration*1000:.2f}ms"
            )
            
            # Store result
            if self.result_store:
                self.result_store(job_id, job.result)
            
            return {
                "success": True,
                "job_id": job_id,
                "result": job.result,
                "latency_ms": duration * 1000
            }
            
        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.now()
            
            logger.error(f"Job {job_id} failed: {e}", exc_info=True)
            
            return {
                "success": False,
                "job_id": job_id,
                "error": str(e)
            }

    def _send_to_sqs(self, job_id: str, user_id: str, stay_points: List[dict]):
        """Send job to SQS queue."""
        # TODO: Implement SQS integration
        pass

    def _get_job_data(self, job_id: str) -> List[dict]:
        """Retrieve job data from storage."""
        # TODO: Implement data retrieval
        return []


class SQSWorker:
    """
    Worker that processes jobs from SQS queue.
    """

    def __init__(
        self, 
        async_serving: AsyncServing,
        poll_interval: int = 5
    ):
        self.async_serving = async_serving
        self.poll_interval = poll_interval
        self.running = False

    def start(self):
        """Start worker loop."""
        self.running = True
        
        while self.running:
            try:
                # Poll for new jobs
                messages = self._poll_sqs()
                
                for message in messages:
                    job_id = message.get("job_id")
                    if job_id:
                        self.async_serving.process_job(job_id)
                
                time.sleep(self.poll_interval)
                
            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
                time.sleep(self.poll_interval)

    def stop(self):
        """Stop worker loop."""
        self.running = False

    def _poll_sqs(self) -> List[Dict]:
        """Poll SQS for new messages."""
        # TODO: Implement SQS polling
        return []


def create_async_server(
    classifier, 
    sqs_queue_url: Optional[str] = None
) -> AsyncServing:
    """
    Factory function to create async server.
    
    Args:
        classifier: Model classifier
        sqs_queue_url: SQS queue URL
        
    Returns:
        AsyncServing instance
    """
    return AsyncServing(classifier, sqs_queue_url)
