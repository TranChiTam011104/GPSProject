# API Contract — GPS Home/Office Inference (Checkpoint 1 / Tuần 2)

This document captures the public HTTP contract for the `gps-home-office-inference`
service. It mirrors the machine-readable spec at [`configs/openapi.yaml`](../configs/openapi.yaml)
(which is auto-generated from the FastAPI app on every release) — keep them in sync.

> **TL;DR** — POST a list of stay-points to `/v1/classify/{user_id}`; receive the
> inferred **home**, **office**, and top-N **POIs** with confidence scores.

---

## Versioning

Every public endpoint is prefixed with `/v{n}/`. Today only **v1** exists; later
versions will be added without breaking v1 clients.

```
/v1/classify/{user_id}   ← current
/v2/classify/{user_id}   ← future (DBSCAN-based, Checkpoint 2)
```

Deprecated versions are announced via the `Sunset` response header (see
:mod:`gps.api.versioned`).

---

## Authentication / Authorisation

**Not implemented yet** — Checkpoint 1 only validates the payload shape.
Production deployment on Cloud Run should sit behind API Gateway with an
IAM authorizer or API key (deferred to Checkpoint 2).

---

## Endpoints

### `GET /health`

Liveness probe — the process is up.

```bash
$ curl http://localhost:8080/health
```

```json
{ "status": "healthy", "version": "0.1.0", "model_version": "v1-heuristic" }
```

| Status | When |
|---|---|
| 200  | Process is responsive |
| 503  | Reserved — would mean the model loader failed |

---

### `GET /ready`

Readiness probe — the classifier singleton is loaded.

```bash
$ curl http://localhost:8080/ready
```

```json
{ "status": "ready", "version": "0.1.0", "model_version": "v1-heuristic" }
```

---

### `POST /v1/classify/{user_id}`

Classify a user's stay-points into **home**, **office**, and **POI** candidates.

#### Request

```json
POST /v1/classify/user_010
Content-Type: application/json

{
  "stay_points": [
    {
      "lat": 39.9847,
      "lng": 116.3184,
      "arrival_time":   "2008-10-23T22:30:00",
      "departure_time": "2008-10-24T06:30:00"
    },
    {
      "lat": 40.1234,
      "lng": 116.5678,
      "arrival_time":   "2008-10-24T09:15:00",
      "departure_time": "2008-10-24T18:15:00"
    }
  ],
  "include_geohash": true
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `stay_points` | array | ✓ | ≥ 1 item |
| `stay_points[].lat` | float [-90, 90] | ✓ | Decimal degrees, WGS84 |
| `stay_points[].lng` | float [-180, 180] | ✓ | Decimal degrees, WGS84 |
| `stay_points[].arrival_time`   | ISO-8601 datetime | ✓ | Naive (GMT) — server converts to Asia/Shanghai before any hour-of-day rule |
| `stay_points[].departure_time` | ISO-8601 datetime | ✓ | Must be > `arrival_time` |
| `stay_points[].altitude_m` | float | ✗ | Optional, currently unused |
| `include_geohash` | bool | ✗ | Default `true` — echoes geohash-6 per location |

#### Response — 200 OK

```json
{
  "user_id": "user_010",
  "locations": [
    {
      "lat": 39.9847,
      "lng": 116.3184,
      "location_type": "home",
      "confidence": 1.0,
      "visit_count": 2,
      "duration_minutes": 960.0,
      "geohash": "wx4eqy"
    },
    {
      "lat": 40.1234,
      "lng": 116.5678,
      "location_type": "office",
      "confidence": 0.857,
      "visit_count": 1,
      "duration_minutes": 540.0,
      "geohash": "wx4uk8"
    }
  ],
  "home":   { "lat": 39.9847, "lng": 116.3184, "location_type": "home",   "confidence": 1.0,   "visit_count": 2, "duration_minutes": 960.0, "geohash": "wx4eqy" },
  "office": { "lat": 40.1234, "lng": 116.5678, "location_type": "office", "confidence": 0.857, "visit_count": 1, "duration_minutes": 540.0, "geohash": "wx4uk8" },
  "pois":   [],
  "model_version": "v1-heuristic",
  "processed_at": "2026-09-22T10:30:00Z"
}
```

#### Errors

| Status | Meaning | Example body |
|---|---|---|
| **400** | Invalid request — bad coords / non-monotonic timestamps / unknown field | `{"detail": "departure_time must be after arrival_time"}` |
| **404** | Reserved for future "user not found" once we onboard persistent storage | `{"detail": "User user_xxx not found"}` |
| **500** | Classifier raised an unexpected exception | `{"detail": "Classification failed"}` (full traceback logged server-side) |

---

### `GET /metrics`

Prometheus exposition format. Includes request counts, latency p50/p95/p99,
and classification counters.

```bash
$ curl http://localhost:8080/metrics
```

```
# HELP gps_inference_requests_total Total requests
# TYPE gps_inference_requests_total counter
gps_inference_requests_total{endpoint="GET:/health"} 1
…
```

---

## Confidence Score — what it really means

**`confidence` is a heuristic, NOT a learned probability.** GeoLife has no
ground-truth home/office labels, so we cannot train a calibrated classifier.

Formula (computed per location type):

```
confidence(winner) = winner_dwell_minutes / total_dwell_minutes_of_type
```

Where:

- `winner`           — the single (lat, lng) bucket that captured the most
                        total dwell minutes (and visits) for this location
                        type.
- `total_dwell_minutes_of_type` — sum of dwell minutes across **all** of
                        the user's stay-points classified as this type
                        (`home` / `office` / `poi`).
- Result is clamped to `[0, 1]`.

Worked example for the request above:

| Stay-point | Hour | Class | Dwell (min) |
|---|---|---|---|
| 1 | 22:30 → 06:30 | home | 480 |
| 2 | 09:15 → 18:15 | office | 540 |

- **home winner** is stay-point 1 → `confidence = 480 / 480 = 1.00`
- **office winner** is stay-point 2 → `confidence = 540 / 540 = 1.00`

If the user had **two** home-classified stay-points (one 480 min, one 100 min):

- `total_dwell = 580 min`
- `winner_dwell = 480 min`
- `confidence = 480 / 580 ≈ 0.828`

Use `confidence` as a **relative ranking signal** — it tells you which
candidate wins each type — not as an absolute probability.

---

## Timezone handling

The server treats `arrival_time` / `departure_time` as **naive GMT** (the
GeoLife convention). Before applying any hour-of-day rule it converts to
**Asia/Shanghai (UTC+8)** via :mod:`gps.data.timezone`. If your data is from
another region, change `TimezoneConverter.__init__` or expose the offset as
a config flag (Checkpoint 2 work).

---

## Status-code summary

| Endpoint | 2xx | 4xx | 5xx |
|---|---|---|---|
| `GET /health`     | 200 | — | 503 |
| `GET /ready`      | 200 | — | 503 |
| `POST /v1/classify/{user_id}` | 200 | 400, 404 | 500 |
| `GET /metrics`    | 200 | — | — |

---

## See also

- [`configs/openapi.yaml`](../configs/openapi.yaml) — machine-readable spec
- [`configs/dev.yaml`](../configs/dev.yaml) — local thresholds
- [`configs/prod.yaml`](../configs/prod.yaml) — production thresholds
- `src/gps/api/main.py` — FastAPI app
- `src/gps/models/heuristic.py` — v1 baseline classifier
- `src/gps/features/stay_point.py` — stay-point detector
