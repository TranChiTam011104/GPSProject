# API service image. Build from the repo root:
#   docker build -f docker/Dockerfile -t gps-inference:latest .

# ── Build stage: runtime dependencies only (requirements.txt) ──
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ──
FROM python:3.11-slim

WORKDIR /app

RUN groupadd -r appgroup && useradd -r -g appgroup appuser

COPY --from=builder /install /usr/local

# The package lives at src/gps; settings read configs/{GPS_ENV}.yaml from /app/configs.
COPY src/ ./src/
COPY configs/ ./configs/

# GPS_MODEL_VERSION picks the classifier (v1 heuristic, v2 DBSCAN places); override with -e.
ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    GPS_ENV=prod \
    GPS_MODEL_VERSION=v1

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:%s/health' % os.environ.get('PORT', '8000'))" || exit 1

# Cloud Run injects PORT (8080); locally it falls back to 8000.
CMD ["sh", "-c", "exec uvicorn gps.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
