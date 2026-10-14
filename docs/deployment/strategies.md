# Deployment strategies (checkpoint 2)

The service classifies a user's home/office from stay-points. Two models exist: **v1** (heuristic, per stay)
and **v2** (DBSCAN places). This page records which rollout strategy fits them, with the evidence.

## What is different about this service

- **Stateless and cheap.** A request is one in-memory classification (~4 ms for v1, ~7 ms for v2), so running
  both models on every request costs almost nothing.
- **No labels, no feedback loop.** GeoLife has no home/office ground truth, and a production caller never tells
  us whether the answer was right. We can measure *agreement* between models, not accuracy.
- **v1 and v2 disagree on about a quarter of users** (notebook 15: same place 76% home / 75% office when both answer).
  A user sent to v2 at random could see their "home" jump to another place, with no criterion that says v2 is right.

## Strategies

| Strategy | What it needs | Fit here |
|---|---|---|
| **Shadow** | A second model run on real requests, results only logged | **Chosen.** Gives real-request evidence at zero user risk; the cost is a few ms of background CPU. |
| **Canary** | A signal from the exposed users (errors, complaints, feedback) to decide whether to widen | **Rejected.** The signal does not exist: wrong answers are silent. Splitting by request would also make one user's home flip between models. |
| **Blue-green** | Two environments and an atomic switch | Used for the **promote** step: flipping `GPS_MODEL_VERSION` v1 -> v2 is one config change, rolled back by flipping it back. |

## How shadow works in this repo

`GPS_MODEL_VERSION=v1` answers. With `GPS_SHADOW_MODEL_VERSION=v2`, the same stay-points are classified by v2 in a
FastAPI background task after the response is sent (`src/gps/api/shadow.py`). A shadow failure is counted and never
reaches the caller. Empty value = shadow off.

Only aggregates are kept: per place type `same_place` (within 200 m, the stay-point radius), `different_place`,
`shadow_only` (v2 answers where v1 is unknown), `primary_only`, `both_unknown`, plus mean latency per model.
**No coordinates are logged or stored** (see `docs/privacy/risk-analysis.md`). Read them at
`GET /v1/shadow/summary` (per instance) or from the `gps.shadow` log lines (all instances, Cloud Logging).

## Result of the shadow run on all users

All 174 users' real stay-points were sent to a v1 service shadowing v2 (container, `GPS_ENV=prod`):

| | home | office |
|---|---|---|
| same place (<= 200 m) | 79 | 69 |
| different place | 25 | 23 |
| v2 answers, v1 unknown | 10 | 16 |
| v1 answers, v2 unknown | 0 | 8 |
| both unknown | 60 | 58 |
| **same-place rate when both answer** | **76.0%** | **75.0%** |
| shadow errors | 0 | 0 |

This equals the offline baseline of notebook 15 (76% / 75%), so the served shadow reproduces the offline
comparison. Mean latency: v1 4.2 ms, v2 7.4 ms.

## Promote

Shadow shows *how* v2 differs, not that it is more correct. The case for v2 is the evidence in notebooks 14-15:
split-half stability 62% / 62% vs v1 41% / 42%, and it answers 114 / 108 users vs 104 / 100. Promotion is the
config flip `GPS_MODEL_VERSION=v2` (new Cloud Run revision, previous revision kept for rollback). Live agreement
that falls far below the 76% / 75% baseline, or a rise in `shadow_errors`, means the request mix differs from
the offline data and the promote should wait.

## Cloud Run

```bash
gcloud builds submit --config cloudbuild.yaml --substitutions _TAG=v1 .     # image gcr.io/<project>/gps-inference:v1
gcloud run deploy gps-inference --image gcr.io/<project>/gps-inference:v1 --region us-central1 \
  --no-allow-unauthenticated --memory 1Gi --max-instances 2 \
  --set-env-vars GPS_MODEL_VERSION=v1,GPS_SHADOW_MODEL_VERSION=v2          # shadow
gcloud run services update gps-inference --region us-central1 \
  --update-env-vars GPS_MODEL_VERSION=v2,GPS_SHADOW_MODEL_VERSION=         # promote
gcloud run services update-traffic gps-inference --region us-central1 --to-revisions <previous>=100   # rollback
```

`.gcloudignore` is required: without it `gcloud builds submit` applies `.gitignore`, whose `models/` rule drops
`src/gps/models/`.
