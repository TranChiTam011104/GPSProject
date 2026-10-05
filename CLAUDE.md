# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

TRACK MLE — Home/Office/POI Inference from GPS traces (VSF Intern, Track B1). Infers a user's home, office, and points-of-interest from raw GPS trajectories (Microsoft GeoLife dataset), exposed via a FastAPI service. The project is organized into three checkpoints (see `README.md` for the full Vietnamese task breakdown):

- **Checkpoint 1** (current, branch `cp1`): stay-point detection, heuristic home/office classifier (v1), OpenAPI spec.
- **Checkpoint 2**: Docker + AWS deploy, model versioning (v1 heuristic vs v2 DBSCAN-based), canary/shadow/blue-green deploy strategies.
- **Checkpoint 3**: sync vs async serving, monitoring/drift/latency dashboards.

Only checkpoint 1 has real, tested implementations today. Most of `src/gps/ml/`, `src/gps/serving/`, `src/gps/monitoring/`, and `src/gps/api/deploy_strategies.py` are checkpoint 2/3 scaffolding (stubs/placeholders), not wired into the running API yet.

## Commands

Run everything with `PYTHONPATH=src` (or `PYTHONPATH` set to the repo's `src/` dir) since the package lives at `src/gps/`, not `src/`.

```bash
pip install -r requirements.txt          # install deps
pip install -e ".[dev]"                  # or via pyproject extras

pytest tests/unit/ -v                    # unit tests
pytest tests/integration/ -v             # integration tests (some hit data/processed/ parquet)
pytest tests/e2e/ -v                     # end-to-end tests
pytest tests/unit/test_features/test_stay_point.py -v          # single file
pytest tests/unit/test_features/test_stay_point.py -k test_name -v  # single test

ruff check src tests                     # lint
mypy src                                 # type check
black src tests && isort src tests       # format

uvicorn gps.api.main:app --reload --host 0.0.0.0 --port 8000   # run API locally (PYTHONPATH=src)
# API docs: http://localhost:8000/docs (Swagger), /redoc, /openapi.json
```

The `Makefile` targets (`make test`, `make lint`, `make format`, `make run`, `make docker-build`, ...) reference `src/api/main.py`, which is stale — the real app is `src/gps/api/main.py`. Prefer the direct commands above; adjust the Makefile if you touch it.

Data processing pipeline (GeoLife raw `.plt` → cleaned Parquet):

```bash
python scripts/run_processing.py                       # full run, all users
python scripts/run_processing.py --user 010 --verbose   # smoke test on one user
python scripts/run_processing.py --clean --workers 2    # wipe output dir first
python scripts/run_processing.py --no-stay-points       # clean points only, skip stay-point detection
python -m gps.data.processing --data-dir data/raw       # same pipeline via the module CLI
```

Notebooks (EDA / evidence) — run with a real kernel and save outputs into the `.ipynb` (needs the `nbclient` dev extra; heavy steps are cached under `notebooks/outputs/<nb>/cache/`, so re-runs are fast):

```bash
python scripts/run_notebooks.py notebooks/07_staypoint_thresholds.ipynb   # one notebook
python scripts/run_notebooks.py notebooks/*.ipynb                        # all of them, in order
```

## Architecture

### Data pipeline (`src/gps/data/processing.py`)

Converts raw GeoLife `.plt` files into partitioned Parquet (`data/processed/users/user_{id}.parquet`), then detects each user's stay-points on all of that user's clean points and writes `data/processed/staypoints/user_{id}.parquet` (`stay_points_to_frame`, schema `STAY_POINT_COLUMNS`: GMT `arrival`/`departure`, `arrival_local`/`departure_local` + `tz_name` from the stay's centroid, `duration_minutes`, `observed_minutes`, `num_points`, ...; an empty file means the user was processed and has no stay-point). The stay-point files are the classifier's input. Processes users **sequentially** (not all in parallel) with a `ProcessPoolExecutor` scoped to each user's files, writing+`gc.collect()`-ing after each user — this is a deliberate memory/thermal safeguard (see the module docstring; a prior version OOM'd/overheated the dev machine processing all 182 users at once).

There is **one** cleaning pipeline, `clean_trajectory(plt_path, user_id)`, per `.plt` file: load → physical-bounds filter → resolve duplicate timestamps → remove speed spikes → re-check duplicate groups whose anchors were spikes → clean altitude → segment (time gap or impossible jump) → localize timezone. Its output is the single definition of "clean data" and the only input to stay-point detection and the classifier. The former "full" pipeline (per-point kinematics, a 180 km/h drift filter, transport-mode labels) was deleted: no task in scope used it, and the 180 km/h filter had no evidence and dropped 57% of airplane / 3.6% of train points. Transport-mode labels (`labels.txt`) are read only inside notebooks, for EDA/validation. Re-add such steps only with evidence and a consumer.

`clean_trajectory` returns a tuple `(df | None, quarantined)`. Rows removed for data-quality reasons (not silently dropped) go to `data/processed/quarantine/user_{id}.csv` with a `reason` column:

- Duplicated timestamps (evidence: `notebooks/02_duplicate_timestamps.ipynb`; duplicates only ever occur within a single `.plt` file, so per-file resolution is sufficient). Exact-coordinate duplicates collapse to one row. For differing coordinates, each candidate is checked against the nearest non-duplicate points before/after ("anchors"): valid if both speeds ≤ `impossible_speed_kmh`. Per group:
  - `duplicate_invalid_anchors` — the two anchors are themselves > `impossible_speed_kmh` apart, so no candidate can be valid (triangle inequality) → whole group quarantined; the reason blames the anchors, not the candidates. Because dedup runs before spike removal, an anchor can itself be a spike: `recheck_invalid_anchor_groups` (called in `clean_trajectory` right after `remove_speed_spikes`) re-resolves these groups with the nearest surviving points as new anchors — 13/16 groups are rescued; the 3 left have a sustained shift between the anchors and stay quarantined. Anchors are never removed iteratively: only the spike rule may drop them (notebook 02 §3.3).
  - `duplicate_no_valid_candidate` — no valid candidate → whole group quarantined.
  - `duplicate_ambiguous_candidates` — ≥ 2 valid candidates more than `ambiguous_duplicate_spread_m` (200 m = stay-point radius) apart → whole group quarantined: the choice would change stay-points and two reasonable selection rules disagree on 27/52 such groups, so any pick is a guess.
  - otherwise the valid candidate with the lowest `max(v_in, v_out)` (speeds to the two anchors) is kept; ties fall back to valid altitude first, then file order. This replaced the pure file-order pick after mentor feedback that it was arbitrary; the pick moves a median 0.7 m (P99 9.7 m), so stay-points do not change (notebook 02 part 3). Candidates rejected for speed are written as `duplicate_rejected_candidate`.
  - The speed check only catches gross errors (anchors are a median 15 s away, so a candidate must be ~4.6 km off to fail), which is acceptable because 99.96% of groups have candidates within median 1.4 m / P99 14 m.
  - Per-mode speed limits were evaluated and rejected (`notebooks/01_speed_threshold.ipynb` section 6): GPS noise is ~34 m (P99.9 of 1-s steps), noise-corrected labelled speeds match real-world speeds from external sources, but guessing the mode from the anchor speed rejects 1.2–2.3% of real points (stop-and-go inside the anchor span), and data-percentile limits (walk ≈ 109 km/h) have no physical meaning. Evidence must use real recorded points only — the user rejected interpolation-based approaches.
- `speed_spike` — point i where speed(i-1→i) and speed(i→i+1) are both > `impossible_speed_kmh` but speed(i-1→i+1) is not. Sustained fast motion is kept; an A-B-A-B alternation region is removed entirely except its endpoints.

Thresholds live in `CleaningThresholds`. **Every threshold must be justified by evidence** (a notebook), not picked ad hoc:

- `impossible_speed_kmh = 1100` — between the fastest verified real point (airplane, 1,048.1 km/h) and the slowest verified GPS error (1,122.7 km/h); `notebooks/01_speed_threshold.ipynb`.
- `max_gap_seconds = 1200` — between within-trip gap P99.9 (252 s) and P99.99 (2,170 s), gaps measured within a file; `notebooks/03_segment_gap_threshold.ipynb`. Gaps cannot find trip boundaries (55.4% of labelled boundaries have gap ≤ 5 s), so segments are for centroid/visualization, not trips.
- `ambiguous_duplicate_spread_m = 200` — reuses the stay-point radius; decision evidence in `notebooks/02_duplicate_timestamps.ipynb`.
- Stay-point `time_threshold_minutes = 30`, `distance_threshold_meters = 200`, `MAX_GAP_HOURS = 18` — notebooks 07 and 04 (see the stay-point section).
- `HeuristicClassifier._bucket_decimals` and the classifier's hour windows are still unjustified placeholders.

`segment_trajectories` starts a new segment when the gap exceeds `max_gap_seconds` **or** the step speed exceeds `impossible_speed_kmh`. Jumps that are not single-point spikes are kept but disconnected (`notebooks/08_trajectory_jumps.ipynb`): 58 multi-point excursions (up to ~19,000 points / 15 h) touch only 11 stay-points (0.03% of dwell) and a "familiar place" test cannot tell which side is wrong; 250 one-sided shifts (median 1.8 km in 4 s, both sides mostly at places the user visits elsewhere) look like timing glitches at signal re-acquisition, and a stay-point cannot straddle them. No extra cleaning rule — any rule would need an unevidenced block-size threshold. `sub_trip_id`s are made globally unique as `{user_id}_{plt_stem}_{segment}` to avoid collisions across users/files.

GeoLife `.plt` timestamps are **naive GMT**. `gps/data/timezone.py::localize_by_location` looks up each point's IANA timezone from its coordinates (`timezonefinder`, offline, cached per 0.01° cell) into `tz_name`, and writes the local wall-clock time (DST aware) as a **naive** `timestamp_local` (one pandas column can hold only one timezone); the GMT `datetime` column is kept for audit. Not a fixed UTC+8: 2.61% of points (16 users; 160 and 172 mostly abroad) are under another offset, and fixed UTC+8 puts 21.5% of their activity at 01–05 h local vs 7.4% by location (reference 5.7%) — `notebooks/09_timezone_by_location.ipynb`. Not by longitude either: China spans ~5 geographic zones but uses one.

### Stay-point detection (`src/gps/features/stay_point.py`)

`StayPointDetector.detect()` runs a sliding window over a sorted trajectory, supporting two distance modes (`DistanceMode.CENTROID`, the default — all points within `distance_threshold_meters` of the running centroid, recalculated per point; `DistanceMode.ANCHOR` — classic Li et al. 2008, all points within threshold of the window's first point; equivalent on the notebook-07 metrics: recall 49.3% vs 50.6%, 3.47 vs 3.52 false stays per 100 vehicle-hours). A window qualifies as a stay-point once its time span reaches `time_threshold_minutes`; scanning resumes just past the window. Thresholds 200 m / 30 min (CENTROID mode) — the GeoLife literature values — are validated on clean, file-chained data in `notebooks/07_staypoint_thresholds.ipynb` against labelled trips (negative control: vehicle trips ≤ 3 h; positive control: stops between consecutive labelled trips; long "walk" labels are too noisy to use). 30 min is the largest value that still finds 30–45 min stops, with 3.5 false stays per 100 vehicle-hours (102 at 5 min, 7.3 at 20 min). 200 m covers the stationary footprint (median per-stop P90 136 m); above 200 m recall and false stays both grow roughly linearly, so the radius is reasonable rather than optimal (300 m would be equally defensible). Pass **all of a user's points** to `detect()` (all `.plt` files concatenated, or the API's point sequence): it first cuts the trajectory at every gap > `max_gap_hours` (default `MAX_GAP_HOURS` = 18 h) between consecutive points, so windows never span such a gap. Because GeoLife files never overlap in time, this equals chaining consecutive files whose gap is ≤ 18 h, plus a cut at the rare > 18 h gap inside one file, and needs no `source_file` column. `max_gap_hours=None` disables the cut — only for notebooks that reproduce the wrong ways below or do their own chaining (04, 05 S0, 06). Not per `sub_trip_id`, not per single file, and never without the gap cut:

- Not per segment: gating by the 20-minute segment gap would split long stays within a recording.
- Not all files concatenated without a gap cut: the detector joins recordings days or years apart that happen to start near where the previous one ended (e.g. a "4-year" stay-point for user 055 built from ~7 minutes of data). The 30-minute threshold is a **minimum** duration, so the gap limit has to come from `max_gap_hours`.
- Not per single file: when the user stops recording in the evening and resumes at the same place next morning, the night falls *between* two files and is lost.
- Why 18 h (`notebooks/04_file_boundaries.ipynb`): the share of next files starting within 200 m of the previous end falls with the gap and first reaches the > 24 h plateau (19.7% ± 1.5%, i.e. mere habit of returning to familiar places) at 18 h. Chaining raises night stays 395 → 3,340 and cuts users without any night stay 96 → 41; recovered nights coincide with observed night places 49.5% vs 18.7–24.3% for daytime stays. No distance condition is needed when chaining — the detector's own 200 m check prevents a window from crossing a boundary where the next file starts far away. The added time is unobserved, which `observed_minutes` exposes.

CENTROID windows keep short approach/leave tails: 68.5% of stays have a point > 200 m from the final centroid, because each point is only checked against the centroid at the moment it joins. Trimming them was measured and rejected (`notebooks/07_staypoint_thresholds.ipynb` section 4): it moves the centroid a median 14 m (below GPS noise), arrival/departure by < 0.3 min, recall −0.3 pt and false stays −5%, so an extra rule buys nothing measurable.

Stay-point correctness (`notebooks/10_staypoint_validation.ipynb`): all 18,597 stays satisfy 9 required properties (mutation-tested; same checks in `test_stay_points_satisfy_detector_definition`), and a blind audit of 60 stratified stays by the user gives precision 92% (95% CI 75–98%), 90.6% of dwell time correct. The only error type is slow movement along a road for 30–45 min; a shape criterion could filter it but needs its own evidence — revisit only if the classifier is affected. Audit page: https://claude.ai/artifact/2ncyaQ5UxAppi4fvmTN9i3 (verdicts in its db collection `verdicts`).

Cleaning barely moves stay-points (`notebooks/05_staypoint_cleaning_impact.ipynb`, all users): file chaining is the decisive step (joining all files gave stays up to 1,459 days), duplicate resolution changes 0.8% of stays (mostly by ~1 m; the rest are stays re-joined once an ambiguous group is quarantined, or windows sitting exactly at the 200 m edge), spike removal changes none. 7 users have no stay-point at all, so the classifier needs an "unknown" result. Shared recordings (`notebooks/11_shared_recordings.ipynb`, documentation only): 821 `.plt` files are byte-identical across 52 users (12% of clean points; 057/094/150 have identical datasets). Users stay independent by project decision — a folder's data belongs to that user. Evidence points mostly to real joint activity (shared files sit at the members' own places; pairs co-locate on separate devices 39% vs 1.1% of pairs). When evaluating the classifier or splitting train/test, group users that share files to avoid double counting and leakage.

Gaps (no GPS points for > 20 min) *inside* a stay-point are deliberately **not** split: `notebooks/06_gaps_inside_staypoints.ipynb` shows the device resumes a few tens of metres from where it stopped, labelled trips fall entirely inside such gaps in only 0.2–1.9% of cases, and cutting at 1–3 h would drop 27–55% of dwell-time. Each `StayPoint` therefore carries both `duration_minutes` (arrival→departure) and `observed_minutes` (excluding gaps > `unobserved_gap_seconds` = 1200 s), so downstream consumers can check sensitivity to unobserved time.

### Classification (`src/gps/models/`)

`BaseClassifier` (in `models/base.py`) defines the `predict(stay_points) -> ClassificationResult` contract shared by v1 (heuristic, implemented) and v2 (DBSCAN + heuristic, scaffolding in `models/cluster.py`). Inputs are normalized through `coerce_stay_points()` / `StayPointInput.from_dict()` (API models, pipeline rows, or `StayPoint` objects).

`HeuristicClassifier` (`models/heuristic.py`, v1) buckets stay-points by rounded lat/lon to absorb GPS jitter, classifies each by the local hour of its arrival — local time from the stay's location via `gps.data.timezone.local_times` (inputs are naive GMT; using GMT hours mislabelled home for 152/174 users) — (`home_hour_start/end` wraps midnight, `office_hour_start/end` restricted to `work_days`), then picks the highest-total-dwell-time bucket per type as the winner. **Confidence is heuristic, not a learned probability**: `confidence = winner_dwell_time / total_type_dwell_time` — this is a deliberate design decision because GeoLife has no ground-truth home/office labels (documented in both `models/base.py` and `api/schemas.py` docstrings).

Longitude is `lon` everywhere (`StayPoint`, `Location`, parquet columns). Some older tests/fixtures (e.g. `tests/conftest.py`) still use `lng` — fix them to `lon` rather than adding aliases.

### API (`src/gps/api/main.py`)

FastAPI app factory (`create_app()`) — module-level `app` object for `uvicorn gps.api.main:app`. Endpoints: `GET /health`, `GET /ready`, `POST /v1/classify/{user_id}` (main classification endpoint, versioned in the URL per the checkpoint-1 spec), `GET /metrics` (Prometheus). Classifier selection happens via `api/dependencies.py::get_classifier` (keyed by `GPS_MODEL_VERSION`). The classify endpoint takes **stay-points only** (`api/schemas.py::StayPointInput`: `lat`, `lon`, `arrival_time`, `departure_time` as naive GMT — tz-aware input is converted — plus optional `observed_minutes`, `altitude_m`), the same shape the pipeline writes to `data/processed/staypoints/`. Raw GPS points are rejected with 422: detection belongs to the pipeline. In the model layer, `coerce_stay_points()` / `StayPointInput.from_dict()` accept API models, pipeline rows (`arrival`/`departure` column names) and `StayPoint` objects.

### Config (`src/gps/config/settings.py`)

Layered Pydantic Settings: module defaults → `configs/{GPS_ENV}.yaml` (default `configs/dev.yaml`) → `GPS_`-prefixed env vars → `.env`. `get_settings()` is `lru_cache`d — restart the process (or clear the cache) to pick up config changes in tests. Nested blocks (`stay_point`, `clustering`, `classification`, `api`) only load from YAML, not flat env vars.

### Privacy (`src/gps/privacy/anonymizer.py`)

`PrivacyAnonymizer` implements geohash spatial generalization, k-anonymity checking/enforcement (`generalize_for_k_anonymity` walks precision down until the k-threshold is met), Laplace-noise differential privacy, and SHA-256 user-ID pseudonymization. Ties into the privacy risk-analysis deliverable in `docs/privacy/risk-analysis.md`.

### Notebooks vs. production code

Notebooks are EDA / design-validation only; production never imports them. `notebooks/README.md` is the index: one notebook per decision, numbered in dependency order (01 speed threshold → 02 duplicates → 03 segment gap → 04 file boundaries → 05 cleaning impact on stay-points → 06 gaps inside stay-points → 07 stay-point thresholds → 08 jumps → 09 timezone → 10 stay-point validation → 11 shared recordings), each citing the `src/` code it justifies. Conventions: narrative in Vietnamese markdown; code, file names, figure/axis titles and table columns in English; outputs under `notebooks/outputs/<notebook>/{figures,tables,cache,maps}` with `cache/` and `maps/` git-ignored. `notebooks/archive/` holds superseded early exploration (the original cleaning prototype and the old stay-point threshold notebook). When a decision changes, update its notebook first, then `src/`.

## Notes

- The dev environment is the `gps` conda env — run `conda activate gps` before any Python command.
- Keep code clean: delete unused code outright instead of leaving it commented out or dead.
- Raw GeoLife data is expected at `data/Geolife Trajectories 1.3/Data/{user}/Trajectory/*.plt` (some local scripts/notebooks use `data/raw/{user}/`); `data/` is gitignored. `tests/integration/test_pipeline_on_real_data.py` looks in both places and skips when neither exists.
- Tests are real pytest tests (`def test_*` + asserts). Don't add exploratory scripts under `tests/` named `test_*.py` — pytest imports them at collection time and one missing data file breaks the whole run; put them in `scripts/` or a notebook instead.

- Python >=3.10, package sources under `src/gps/` (installed via `[tool.setuptools.packages.find] where = ["src"]`), tests under `tests/{unit,integration,e2e}/`.
- `pytest.ini_options` in `pyproject.toml` sets `asyncio_mode = "auto"` and `addopts = "-v --tb=short"` — no need to pass `-v` manually.
- Two geospatial libs are used for encoding: `geohash2` (geohash strings, used throughout API/privacy/features) and `h3` (Uber's hex grid, `features/h3_features.py` — currently a thin placeholder wrapper, not integrated into the classifiers).
- `docker/` holds `Dockerfile`, `Dockerfile.worker`, `docker-compose.yml`, and an nginx config for the checkpoint-2 deploy work; not required for local dev.
