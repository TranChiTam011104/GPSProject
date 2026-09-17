# Data
DATA_DIR := data
RAW_DIR := $(DATA_DIR)/raw
PROCESSED_DIR := $(DATA_DIR)/processed

# Source
SRC_DIR := src

# Python
PYTHON := python3
PYTEST := pytest
PYTHONPATH := $(SRC_DIR)

# Docker
DOCKER_IMAGE := gps-inference-api
DOCKER_TAG := latest

# AWS
AWS_REGION := us-east-1

# Model
MODEL_VERSION ?= v1

.PHONY: help install setup test test-unit test-integration test-e2e lint format clean run docker-build docker-run docker-stop api-docs

## help: Show this help message
help:
	@echo "TRACK MLE - GPS Home/Office Inference"
	@echo ""
	@echo "Available targets:"
	@sed -n 's/^##//p' $(MAKEFILE_LIST) | column -t -s ':' | sed -e 's/^/ /'

## install: Install dependencies
install:
	$(PYTHON) -m pip install -r requirements.txt

## setup: Setup development environment
setup: install
	@echo "Creating necessary directories..."
	-mkdir -p $(RAW_DIR)/geolife $(RAW_DIR)/gowalla $(RAW_DIR)/brightkite
	-mkdir -p $(PROCESSED_DIR)/cleaned_traces $(PROCESSED_DIR)/stay_points
	-mkdir -p models/v1 models/v2
	@echo "Environment ready!"

## test: Run all tests
test: test-unit test-integration test-e2e

## test-unit: Run unit tests
test-unit:
	$(PYTEST) tests/unit/ -v --cov=$(SRC_DIR) --cov-report=term-missing

## test-integration: Run integration tests
test-integration:
	$(PYTEST) tests/integration/ -v

## test-e2e: Run end-to-end tests
test-e2e:
	$(PYTEST) tests/e2e/ -v

## lint: Run linters
lint:
	ruff check $(SRC_DIR) tests/
	mypy $(SRC_DIR)

## format: Format code
format:
	black $(SRC_DIR) tests/
	isort $(SRC_DIR) tests/

## clean: Clean temporary files
clean:
	rm -rf build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf htmlcov .coverage

## run: Run the API locally
run:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

## docker-build: Build Docker image
docker-build:
	docker build -f docker/Dockerfile -t $(DOCKER_IMAGE):$(DOCKER_TAG) .

## docker-run: Run Docker container
docker-run:
	docker run -p 8000:8000 --env-file .env $(DOCKER_IMAGE):$(DOCKER_TAG)

## docker-stop: Stop Docker container
docker-stop:
	docker stop $(DOCKER_IMAGE) || true

## api-docs: Open API documentation
api-docs:
	@echo "API docs available at: http://localhost:8000/docs"

## download-data: Download GeoLife dataset
download-data:
	$(PYTHON) scripts/download_geolife.py

## benchmark: Run sync vs async benchmark
benchmark:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/benchmark.py

## mlflow: Start MLflow UI
mlflow:
	mlflow ui --backend-store-uri sqlite:///mlflow.db

## migrate-v1-v2: Migrate model from v1 to v2
migrate-v1-v2:
	@echo "Running migration from heuristic (v1) to DBSCAN (v2)..."
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -c "from src.ml.registry import ModelRegistry; r = ModelRegistry(); r.migrate_version('v1', 'v2')"
