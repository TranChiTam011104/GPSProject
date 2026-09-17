# Sync vs Async Serving Analysis

## Overview

This document compares synchronous and asynchronous serving patterns for the GPS inference API.

---

## Synchronous Serving

**Pattern**: Request → Process → Response (immediate)

```
Client ──── Request ────▶ API ──── Process ────▶ Model ────▶ Result
         ◀──────────── Response ◀──────────────┘
```

### Characteristics

| Aspect | Description |
|--------|-------------|
| Latency | Low (~50-200ms) |
| Throughput | Limited by request time |
| Complexity | Simple |
| Scalability | Vertical (bigger machines) |
| Use Case | Real-time, interactive |

### When to Use

- User-facing applications
- Real-time classification
- Low-latency requirements (<500ms)
- Simple request/response flows

### Example

```python
from src.serving.sync import SyncServing

server = SyncServing(classifier)

result = server.serve(user_id, stay_points)
# Immediate response
```

---

## Asynchronous Serving

**Pattern**: Request → Queue → Worker → Result (polling/callback)

```
Client ──── Request ────▶ Queue ────▶ Worker ────▶ Model
    │                                   │
    │◀────────── Poll/Callback ◀────────┘
    │
    │                    (Later)
    ▼
Result
```

### Characteristics

| Aspect | Description |
|--------|-------------|
| Latency | Variable (seconds to minutes) |
| Throughput | High (batch processing) |
| Complexity | Higher (queue + workers) |
| Scalability | Horizontal (more workers) |
| Use Case | Batch, high-volume processing |

### When to Use

- Batch processing many users
- Heavy computation
- Background jobs
- Non-interactive applications

### Example

```python
from src.serving.async_serving import AsyncServing

server = AsyncServing(classifier, sqs_queue_url=SQS_URL)

# Submit job
job_id = server.submit_job(user_id, stay_points)

# Poll for result
while True:
    job = server.get_job_status(job_id)
    if job.status == 'completed':
        result = job.result
        break
    sleep(5)
```

---

## Comparison

| Criteria | Sync | Async |
|----------|------|-------|
| Response Time | Immediate | Delayed |
| Scalability | Vertical | Horizontal |
| Complexity | Low | High |
| Cost | Lower (simple) | Higher (infrastructure) |
| Reliability | Request fails = user error | Can retry failed jobs |
| User Experience | Instant | Requires polling |

---

## Latency Benchmarks

Based on typical workloads:

| Operation | Sync | Async |
|-----------|------|-------|
| Single User | 50-150ms | 5-60s (including queue) |
| 100 Users | 5-15s (sequential) | 10-30s (parallel) |
| 1000 Users | 50-150s | 1-5min (batch) |

---

## Recommendation for This Project

**Use Sync for**: API endpoints (real-time user requests)

**Use Async for**: Batch classification of user datasets

### Hybrid Approach

```python
# API endpoint uses sync serving
@app.post("/v1/classify/{user_id}")
async def classify_user(user_id: str, data: Request):
    return sync_server.serve(user_id, data.stay_points)

# Background job uses async
@app.post("/batch/classify")
async def batch_classify(data: BatchRequest):
    job_ids = []
    for user_data in data.users:
        job_id = async_server.submit_job(user_data)
        job_ids.append(job_id)
    return {"job_ids": job_ids}
```

---

## AWS Implementation

### Sync (API Gateway + Lambda/EC2)

```
Client → API Gateway → Lambda/EC2 → Response
```

### Async (API Gateway + SQS + Lambda)

```
Client → API Gateway → SQS Queue → Lambda Worker → DynamoDB
```
