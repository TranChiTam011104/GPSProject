"""FastAPI app for the GPS Home/Office inference API.

Checkpoint 1 / Tuần 2 deliverable — exports the OpenAPI spec at `/openapi.json`
and Swagger UI at `/docs`. The classification endpoint accepts stay-points
(emitted by the stay-point detector from the user's GPS trajectory) and
returns the inferred home/office/POIs with confidence scores.

Run locally:
    PYTHONPATH=src python -m gps.api.main
or:
    uvicorn gps.api.main:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from gps.api.dependencies import get_classifier, get_model_version
from gps.api.schemas import (
    ClassificationRequest,
    ClassificationResponse,
    ErrorResponse,
    HealthResponse,
)
from geohash2 import encode as geohash_encode
from gps.config.settings import get_settings
from gps.monitoring.logger import RequestLogger
from gps.monitoring.metrics import MetricsCollector

logger = logging.getLogger("gps.api")
logging.basicConfig(level=os.getenv("GPS_LOG_LEVEL", "INFO"))


# ── Lifespan + metrics singletons ────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Starting %s (env=%s, model=%s)",
                settings.GPS_APP_NAME, settings.GPS_ENV, settings.GPS_MODEL_VERSION)
    yield
    logger.info("Shutting down")


metrics = MetricsCollector()
request_logger = RequestLogger()


# ── App factory ──────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.GPS_APP_NAME,
        version=settings.GPS_APP_VERSION,
        description=(
            "API for inferring **Home / Office / POI** locations from GPS "
            "stay-points.\n\n"
            "- **v1** — heuristic-on-stay-points (baseline)\n"
            "- **v2** — DBSCAN cluster then heuristic (noise-robust)\n\n"
            "Confidence is heuristic (no supervised ground-truth available)."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_routes(app)
    register_middleware(app)
    register_exception_handlers(app)
    return app


def register_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.time()
        req_id = request.headers.get("X-Request-ID", "unknown")
        try:
            response = await call_next(request)
        except Exception as exc:  # pragma: no cover - defensive
            duration = time.time() - start
            metrics.record_error(path=request.url.path)
            request_logger.log_error(req_id, str(exc), path=request.url.path)
            logger.exception("Request failed: %s", exc)
            raise
        duration = time.time() - start
        metrics.record_request(
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration=duration,
        )
        request_logger.log_request(
            request_id=req_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration * 1000,
        )
        return response


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):  # pragma: no cover
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ── Routes ───────────────────────────────────────────────────────────────────


def register_routes(app: FastAPI) -> None:
    @app.get("/health", response_model=HealthResponse, tags=["Health"])
    async def health_check():
        return HealthResponse(
            status="healthy",
            version=get_settings().GPS_APP_VERSION,
            model_version=get_model_version(),
        )

    @app.get("/ready", response_model=HealthResponse, tags=["Health"])
    async def readiness_check():
        # No expensive warm-up yet — v1/v2 are stateless.
        return HealthResponse(
            status="ready",
            version=get_settings().GPS_APP_VERSION,
            model_version=get_model_version(),
        )

    @app.post(
        "/v1/classify/{user_id}",
        response_model=ClassificationResponse,
        responses={
            400: {"model": ErrorResponse, "description": "Invalid request"},
            500: {"model": ErrorResponse, "description": "Internal error"},
        },
        tags=["Classification"],
        summary="Classify a user's locations (home/office/POI)",
    )
    async def classify_user(
        user_id: str,
        request: ClassificationRequest,
        classifier=Depends(get_classifier),
    ):
        try:
            result = classifier.predict(request.stay_points)
            # Stamp the user_id (which the classifier doesn't know about).
            result.user_id = user_id

            # Stay-point inputs may be Pydantic objects or dicts depending on
            # the caller; normalise so the response schema gets plain dicts.
            def _to_dict(loc):
                d = loc.to_dict()
                # Re-derive geohash lazily if it wasn't set by the classifier.
                if d.get("geohash") is None:
                    d["geohash"] = geohash_encode(d["lat"], d["lng"], precision=6)
                # Drop zero-valued metadata that callers didn't supply so the
                # output reads cleanly (e.g. altitude_m=0.0 -> omitted).
                if d.get("altitude_m") in (0, 0.0, None):
                    d.pop("altitude_m", None)
                return d

            return ClassificationResponse(
                user_id=user_id,
                locations=[_to_dict(loc) for loc in result.locations],
                home=_to_dict(result.home) if result.home else None,
                office=_to_dict(result.office) if result.office else None,
                pois=[_to_dict(loc) for loc in result.pois],
                model_version=classifier.get_model_version(),
                processed_at=result.processed_at,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:  # pragma: no cover
            logger.exception("Classification failed for user %s", user_id)
            raise HTTPException(status_code=500, detail="Classification failed")

    @app.get("/metrics", tags=["Monitoring"])
    async def prometheus_metrics():
        return metrics.get_metrics()


# Module-level ASGI app for `uvicorn gps.api.main:app`.
app = create_app()


def run() -> None:
    """Console-script entry: ``gps-api``."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "gps.api.main:app",
        host=settings.api.host,
        port=settings.api.port,
        workers=settings.api.workers,
        log_level=settings.api.log_level.lower(),
    )


if __name__ == "__main__":  # pragma: no cover
    run()
