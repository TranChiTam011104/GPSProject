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

The URL version is the version of the **contract**. The **model** behind it is chosen by
`GPS_MODEL_VERSION` and reported in each response's `model_version`; both models return the
same schema:

| `GPS_MODEL_VERSION` | `model_version` | What is scored |
|---|---|---|
| `v1` (default) | `v1-heuristic` | each stay-point on its own (`notebooks/12`, `13`) |
| `v2` | `v2-cluster-dbscan` | places: stay-points grouped by DBSCAN (`eps` 150 m, `min_samples` 2), scored by the window minutes of all their stays (`notebooks/14_place_clustering.ipynb`) |

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
    { "lat": 39.9847, "lon": 116.3184, "arrival_time": "2008-10-22T14:30:00", "departure_time": "2008-10-22T22:30:00" },
    { "lat": 39.9847, "lon": 116.3184, "arrival_time": "2008-10-23T14:30:00", "departure_time": "2008-10-23T22:30:00",
      "observed_minutes": 412.5 },
    { "lat": 40.1234, "lon": 116.5678, "arrival_time": "2008-10-23T01:00:00", "departure_time": "2008-10-23T10:00:00" },
    { "lat": 40.1234, "lon": 116.5678, "arrival_time": "2008-10-24T01:00:00", "departure_time": "2008-10-24T10:00:00" }
  ]
}
```

The endpoint takes **stay-points only**, in the shape the pipeline writes to
`data/processed/staypoints/user_{id}.parquet` (columns `arrival` / `departure` there).
Raw GPS points are not accepted: stay-point detection runs in the pipeline, where its
thresholds are validated.

| Field | Type | Required | Notes |
|---|---|---|---|
| `stay_points` | array | ✓ | ≥ 1 item |
| `stay_points[].lat` | float [-90, 90] | ✓ | Stay centroid, decimal degrees, WGS84 |
| `stay_points[].lon` | float [-180, 180] | ✓ | Stay centroid, decimal degrees, WGS84 |
| `stay_points[].arrival_time`   | ISO-8601 datetime | ✓ | Naive = GMT (GeoLife convention); tz-aware values are converted to GMT |
| `stay_points[].departure_time` | ISO-8601 datetime | ✓ | Must be > `arrival_time` |
| `stay_points[].observed_minutes` | float ≥ 0 | ✗ | Minutes actually covered by GPS points; ≤ departure − arrival |
| `stay_points[].altitude_m` | float | ✗ | Mean altitude, metres |

#### Response — 200 OK

```json
{
  "user_id": "user_010",
  "locations": [
    {
      "lat": 39.9847,
      "lon": 116.3184,
      "location_type": "home",
      "confidence": 1.0,
      "visit_count": 2,
      "duration_minutes": 960.0,
      "geohash": "wx4eqy"
    },
    {
      "lat": 40.1234,
      "lon": 116.5678,
      "location_type": "office",
      "confidence": 0.857,
      "visit_count": 1,
      "duration_minutes": 540.0,
      "geohash": "wx4uk8"
    }
  ],
  "home":   { "lat": 39.9847, "lon": 116.3184, "location_type": "home",   "confidence": 0.5, "visit_count": 1, "duration_minutes": 480.0, "geohash": "wx4eqy" },
  "office": { "lat": 40.1234, "lon": 116.5678, "location_type": "office", "confidence": 0.5, "visit_count": 1, "duration_minutes": 540.0, "geohash": "wx4uk8" },
  "home_status":   { "status": "found", "reason": null, "window_minutes": 480.0, "support": 2 },
  "office_status": { "status": "found", "reason": null, "window_minutes": 540.0, "support": 2 },
  "pois":   [],
  "model_version": "v1-heuristic",
  "processed_at": "2026-09-22T10:30:00Z"
}
```

#### Unknown home / office

`home` and `office` are decided **separately**, and each is `null` when it is unknown;
`home_status` / `office_status` say why and keep the evidence:

| Field | Meaning |
|---|---|
| `status` | `found` (the location is given) or `unknown` (the location is `null`) |
| `reason` | `null` when found. Otherwise `no_candidate` (no stay-point has any minute inside the window), `too_few_window_minutes` (the best candidate has fewer than 240 minutes inside the window) or `one_off_place` (v1: no other stay-point with window minutes lies within 200 m of the best one; v2: the best place has window minutes on a single day) |
| `window_minutes` | Minutes of the best candidate (v1: a stay-point; v2: all stays of a place) inside the window; `null` without candidates |
| `support` | How many times the user was at that place inside the window. v1: stay-points within 200 m of the best one, itself included; v2: distinct days (nights for home) with window minutes at the place. `null` without candidates |

Evidence: `notebooks/13_minimum_evidence.ipynb` split each user's data in two halves and
ran v1 on each. Below these two minimums the two halves agree no more often than random
candidates do (home 15–19% vs 11–21%; one-off winners 19–24% vs 17–21%), and more data does
not help because full nights tie. A user is never dropped: a user with only a home (or only an
office) is a valid result. Applied to the 174 users that have stay-points, home is answered for
104 and office for 100 (164 / 159 without these two minimums).

The single `confidence` score does **not** replace these fields: in the same experiment a
higher v1 confidence did not mean a more repeatable answer.

**v2** (`notebooks/14_place_clustering.ipynb`) uses the same 240-minute minimum and counts
**days** instead of nearby stays: a place seen on one day only repeats on the other half about
as often as a random candidate (34% / 36% vs 20%), from 5 days on it repeats 80–100% of the
time. v2 answers home for 114 users and office for 108, and its answers repeat more often than
v1's (62% / 62% vs 41% / 42%).

#### Errors

| Status | Meaning | Example body |
|---|---|---|
| **422** | Invalid request — empty list, missing time, raw GPS point, departure not after arrival, `observed_minutes` > duration | FastAPI validation body naming the field, e.g. `departure_time must be after arrival_time` |
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
confidence(winner) = winner_window_minutes / total_window_minutes_of_type
```

Where:

- `window minutes`  — minutes a stay-point spends inside the type's daily
                        window in local time: `home` 22:00–08:00 every day,
                        `office` 09:00–18:00 on Mon–Fri. A stay arriving at
                        20:00 and staying the night counts as home.
- `winner`          — the stay-point with the most window minutes (model v1
                        scores each stay-point on its own; ties go to the
                        longer, then the earlier stay).
- `total_window_minutes_of_type` — sum of window minutes across **all** of
                        the user's stay-points for this type. `poi` uses
                        plain dwell minutes of stay-points outside both windows.
- Result is clamped to `[0, 1]`.

Worked example for the request above:

| Stay-point | Local time | Window minutes |
|---|---|---|
| 1 | 22:30 → 06:30 | home 480 |
| 2 | 09:15 → 18:15 | office 540 (weekday) |

- **home winner** is stay-point 1 → `confidence = 480 / 480 = 1.00`
- **office winner** is stay-point 2 → `confidence = 540 / 540 = 1.00`

(Each is reported as `found` only when the place repeats — see *Unknown home / office*;
a single stay-point per type, as here, would be a `one_off_place`.)

If the user had **two** stay-points with home minutes (480 and 100):

- `total = 580 min`
- `winner = 480 min`
- `confidence = 480 / 580 ≈ 0.828`

Use `confidence` as a **relative ranking signal** — it tells you which
candidate wins each type — not as an absolute probability.

---

## Timezone handling

The server treats `arrival_time` / `departure_time` as **naive GMT** (the
GeoLife convention) and converts tz-aware input to GMT. Before any hour-of-day rule,
the classifier converts arrival and departure to **local time at the stay's location** (IANA time
zone looked up from the coordinates, daylight saving included), the same rule the
pipeline uses for `arrival_local`. Output timestamps (`first_seen`, `last_seen`) stay in GMT.

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
