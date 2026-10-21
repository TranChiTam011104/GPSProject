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
| **Blue-green** | Two environments side by side, the new one verified before an atomic switch | **Not used.** The only thing that changes is which model one image selects, so a second environment buys nothing. Promote is a plain config change (below); no pre-switch verification on a separate copy was done. |

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

The same run against Cloud Run (revision `gps-inference-00005`, private, `GPS_MODEL_VERSION=v1`,
`GPS_SHADOW_MODEL_VERSION=v2`, 2026-10-14) gave identical counts, 0 shadow errors, and 174 `gps.shadow` log
lines in Cloud Logging without coordinates. Mean latency on Cloud Run: v1 9.7 ms, v2 10.0 ms. All 174 background
tasks completed under request-based billing, so `--no-cpu-throttling` was not needed at this load.

## Promote

Shadow shows *how* v2 differs, not that it is more correct. The case for v2 is the evidence in notebooks 14-15:
split-half stability 62% / 62% vs v1 41% / 42%, and it answers 114 / 108 users vs 104 / 100. Promotion is the
config flip `GPS_MODEL_VERSION=v2` (new Cloud Run revision, previous revision kept for rollback). Live agreement
that falls far below the 76% / 75% baseline, or a rise in `shadow_errors`, means the request mix differs from
the offline data and the promote should wait.

## Versioning

There are no trained artifacts: a "model" is code plus the thresholds in `configs/*.yaml`, so it is versioned by
what already identifies a deploy, not by a registry:

| What | Identity |
|---|---|
| Behaviour | `model_version` string in every response and log line: `v1-heuristic`, `v2-cluster-dbscan` |
| Parameters | `GET /v1/models` returns the active and shadow version and each version's effective thresholds |
| Code + config | image tag in `gcr.io/<project>/gps-inference:<tag>` (immutable digest on the Cloud Run revision) |
| Rollback | the previous Cloud Run revision stays available; traffic can be pointed back at it |

The unused MLflow registry scaffolding (`gps.ml`, the mlflow compose service, `make mlflow`) was removed: with no
artifacts and no experiment tracking in scope it had no consumer. Re-add it only when a trained model exists.

## Promote result (2026-10-14)

The config flip was applied on Cloud Run (`gps-inference-00006`, `GPS_MODEL_VERSION=v2`, shadow off, same image,
previous revision `00005` kept for rollback). `/health` reports `v2`, and users 068 and 010 sent to Cloud Run
match the in-process v2 classifier.

## Least privilege (IAM, 2026-10-19)

Until this change the service ran as the default compute service account, which holds `roles/editor` on the whole
project, and the same account was the Cloud Build identity. The app calls no Google API (config is in the image, logs
go to stdout), so it needed no role at all. Four identities now, one per job, each with the smallest scope:

| Role in the flow | Identity | Permissions (scope) |
|---|---|---|
| Runs the service | `gps-inference-run` | **none** |
| Builds the image | `gps-build` | `artifactregistry.writer` (repo `gcr.io`), `logging.logWriter` (project), `storage.objectViewer` (source bucket) |
| Deploys | `gps-deployer` | `run.developer` (the service), `iam.serviceAccountUser` (only `gps-inference-run`, `gps-build`), `artifactregistry.reader` (repo `gcr.io`), `storage.objectAdmin` + `legacyBucketReader` (source bucket), `cloudbuild.builds.editor`, `serviceusage.serviceUsageConsumer` (project) |
| Calls the API | `gps-client` | `run.invoker` on the service only |

The service stays `--no-allow-unauthenticated`. Build and deploy were run as `gps-deployer` (impersonation), so the
narrow set is proven sufficient: image `gps-inference:v2-lp` → revision `gps-inference-00008`, same code and config
as `00007`, `GPS_MODEL_VERSION=v2`.

Checks:

| Check | Result |
|---|---|
| Call without a token | 403 |
| `gps-client` token → `/health` | 200, `model_version: v2` |
| Roles of `gps-inference-run` on the project | none |
| Deployer tries to reset the service IAM (`gcloud run deploy` does) | refused, service stays private |

Removed: `roles/editor` and `cloudbuild.builds.builder` from the default compute account (nothing uses it now); the
`github-actions` account (MovieLens CI, `run.admin`, `storage.admin`, `iam.securityAdmin`) and its non-expiring JSON key
were disabled, not deleted. The policy before cleanup is kept in `_claude_workspace/deploy/iam_before_cleanup.json`.

Not least-privilege yet: `logging.logWriter`, `cloudbuild.builds.editor` and `serviceUsageConsumer` are bound at
project level; `gcloud builds submit` needs `--gcs-source-staging-dir` because finding the default bucket needs the
project-wide `storage.buckets.list`. A real CI would deploy through Workload Identity Federation, not a key.

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
