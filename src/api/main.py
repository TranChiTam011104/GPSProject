"""
FastAPI application for GPS Home/Office inference API.
"""
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import time
from typing import List, Optional

from src.api.schemas import (
    ClassificationRequest,
    ClassificationResponse,
    HealthResponse,
    ErrorResponse,
    LocationType
)
from src.api.dependencies import get_classifier, get_model_version
from src.monitoring.metrics import MetricsCollector
from src.monitoring.logger import RequestLogger


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Metrics
metrics = MetricsCollector()
request_logger = RequestLogger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting GPS Home/Office Inference API...")
    yield
    logger.info("Shutting down API...")


# Create FastAPI app
app = FastAPI(
    title="GPS Home/Office Inference API",
    description="""
    API for inferring Home, Office, and POI locations from GPS trajectories.
    
    ## Features
    - Stay-point detection from raw GPS data
    - Home/Office classification using time-based heuristics
    - DBSCAN clustering for noise reduction (v2 model)
    - Confidence scoring for classifications
    - Privacy-preserving geohash encoding
    
    ## Models
    - v1: Baseline heuristic (direct time-based rules)
    - v2: DBSCAN clustering + heuristic
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests."""
    start_time = time.time()
    request_id = request.headers.get("X-Request-ID", "unknown")
    
    try:
        response = await call_next(request)
        duration = time.time() - start_time
        
        # Log request
        metrics.record_request(
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration=duration
        )
        
        request_logger.log_request(
            request_id=request_id,
            method=request.method,
            path=str(request.url.path),
            status=response.status_code,
            duration=duration
        )
        
        return response
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Request failed: {e}", exc_info=True)
        metrics.record_error(path=request.url.path)
        raise


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        model_version=get_model_version()
    )


@app.get("/ready", response_model=HealthResponse, tags=["Health"])
async def readiness_check():
    """Readiness check for deployment."""
    try:
        # TODO: Check if model is loaded and ready
        return HealthResponse(
            status="ready",
            version="1.0.0",
            model_version=get_model_version()
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post(
    "/v1/classify/{user_id}",
    response_model=ClassificationResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        404: {"model": ErrorResponse, "description": "User not found"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
    tags=["Classification"],
)
async def classify_user(
    user_id: str,
    request: ClassificationRequest,
    classifier = Depends(get_classifier),
):
    """
    Classify a user's locations as Home, Office, or POI.
    
    Provide GPS trajectory data and receive classified locations
    with confidence scores.
    
    - **user_id**: Unique identifier for the user
    - **stay_points**: List of stay-points with lat, lng, timestamps
    - **model_version**: Optional model version (v1 or v2)
    """
    try:
        result = classifier.predict(request.stay_points)
        return ClassificationResponse(
            user_id=user_id,
            locations=result.locations,
            home=result.home_location,
            office=result.office_location,
            pois=result.poi_locations,
            model_version=classifier.get_model_version(),
            processed_at=result.processed_at
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Classification failed for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Classification failed")


@app.get("/metrics", tags=["Monitoring"])
async def get_metrics():
    """Get Prometheus metrics."""
    return metrics.get_metrics()


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )
