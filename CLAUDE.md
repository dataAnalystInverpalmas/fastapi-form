# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Portal de Datos Inverpalmas: a fullstack app for agricultural production data management. FastAPI backend (Python 3.11) runs ETL pipelines over DBF files served from Windows SMB shares (`\\172.10.18.2\...`), persists results to MySQL/MariaDB, and exports Excel/CSV reports. A Vue 3 (Composition API) + Vite + Tailwind SPA is the primary UI; a legacy Jinja2 UI is still served side by side.

## Commands

### Backend

```bash
# Dev server (from repo root, venv active)
uvicorn main:app --reload
# http://localhost:8000

# Production-style run (workers, no reload)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2

# Run one focused test suite
python -m unittest app.services.tests.test_production_pipeline_generator

# Run all backend tests
venv\Scripts\python.exe -m unittest discover -s app\services\tests -p "test_*.py"
```

Focused suites worth knowing by name (job-specific, in `app/services/tests/`): `test_production_pipeline_generator`, `test_fusarium_pipeline_generator`, `test_qualities_pipeline_generator`, `test_productivity_varieties_report_generator`, `test_proyecciones_generator`, `test_proyectar_rosas_generator`, `test_quipus_vs_proy_generator`, `test_resumir_curvas_usadas_generator`, `test_anomalias_lonas_generator`, `test_load_arre_generator`, `test_dbf_export_csv`, `test_etl_params`, `test_api_etl_jobs_dependencies`, `test_path_resolution`.

**Run `test_production_pipeline_generator` after touching any peak (`pico`) logic** in `production_pipeline_generator.py` — this is a repository rule, not just good practice (see Business rules below).

### Frontend (`frontend/`)

```bash
npm install       # or npm ci
npm run dev        # http://localhost:5173, proxies /api -> :8000
npm run build       # outputs frontend/dist, served by FastAPI under /app/
npm run preview
```

No lint/typecheck script is configured in `frontend/package.json`.

### Docker

```bash
docker compose up --build
```

Builds the frontend, starts MySQL, and serves FastAPI at `http://localhost:8000`. `scripts/entrypoint.sh` mounts **every** CIFS/SMB share listed in `SMB_SHARES` (`produc`, `Usuarios`, `newfact`) on container start — one mount per share at `SMB_MOUNT_ROOT/<share>` — and `/health` reports each one separately. A share that fails to mount does not stop the app; the jobs that read it fail instead, so check `/health` first when a job can't find a file.

The container starts as **root** on purpose: mounting CIFS needs `CAP_SYS_ADMIN` (granted by `cap_add` in `docker-compose.yml`) and an unprivileged user cannot mount. After mounting, `entrypoint.sh` drops to `appuser` via `setpriv` to run uvicorn, so the app itself stays unprivileged. Don't add `USER appuser` back to the Dockerfile — it silently breaks every mount.

## Architecture

### ETL system (`app/services/etl/`)

Registry/catalog/runner pattern, deliberately separated:

- `catalog.py` — the single source of truth: a list of `ETLJobDefinition` (job_id, runner callable, timeout, `depends_on`, `supports_params`/`default_params`, dependency/flow grouping for the UI). **Adding a new job means adding one entry here plus its runner in `etl_jobs/` or `dbf_loaders/`.**
- `registry.py` — lazy-loads the catalog once (`get_job`, `list_jobs`).
- `runner.py` — executes jobs in a `ThreadPoolExecutor` (`ETL_MAX_WORKERS`), enforces per-job timeouts via a nested single-worker executor + future, blocks concurrent runs for jobs with `allows_parallel=False`.
- `repository.py` — persists run state to MySQL (`etl_jobs`, `etl_job_runs`, `etl_job_last_params`); tables are created automatically at startup (`bootstrap_jobs()` in `app/main.py` lifespan). Also sweeps stale/orphaned runs (both at boot and every minute via APScheduler).
- `params.py` — normalizes/coerces user-submitted params against a job's `default_params` shape (int/float/bool/list parsing from strings), and resolves effective params with priority: explicit request > last-saved params for that job > catalog defaults.

Two job families exist and are exposed under different UI/URL sections:
- **Loaders** (`app/services/dbf_loaders/`, `/load/jobs`) — read a DBF straight into a MySQL table (`allows_parallel=False`, no params). Five of these plus `bajas_exportado` run automatically every day at 10:00 (America/Bogota) via APScheduler cron jobs registered in `app/main.py`.
- **Process jobs** (`app/services/etl_jobs/`, `/etl/jobs`) — heavier pipelines that read DBF/CSV/MySQL, transform with pandas, and write CSV/Excel/MySQL. Many declare `depends_on` other job_ids purely for UI/flow-diagram purposes (`/api/etl/flow`); the runner does **not** enforce dependency ordering — the caller/operator is responsible for running jobs in the right order.

Jobs run in background threads and are tracked by a DB-backed run id, not by blocking HTTP requests — routes in `app/routes/api.py` start a job and return immediately; the frontend polls run status (see `useEtlPolling.js`).

### Business rules (do not rediscover from data — these are fixed conventions)

- `ciclo` (cycle) is not the same as `pico` (peak): cycle 1 covers ages 0–35, cycle 2 covers ages 36–70.
- In `production_pipeline_generator.py`, `pico` is the `edad` (age) of the **last point of the best consecutive window** of `f_m`, ordered by `edad`: window size 4 for cycle 1, window size 10 for cycle 2. Detail output computes `pico` per `finca`/`bloque`/`nvariedad`/`cosecha`/`ciclo`; summary output computes it per `finca`/`nvariedad`/`ciclo` after grouping by `edad`.
- `production_pipeline_generator`, `qualities_pipeline`, and `fusarium_pipeline` all append a synthetic `finca` `"000"` to their summaries (production: regroup without `finca` on `nvariedad`/`ciclo`/`edad` and recompute `f_m`/`pico` with the same summary logic) while keeping the original `001`/`002` rows.
- `productivity_varieties_report` **consumes** the `"000"` finca from those upstream summaries — it does not reconstruct it itself.
- In `productivity_varieties_report`, export `ciclo` and `Pico` as separate columns; never use `pic` as a synonym for `pico`.

### Config (`app/core/`)

- `settings.py` — a `pydantic-settings` `Settings` model, loaded from `.env`. It defines every ETL job's file paths, filters, and date ranges as typed fields (mostly UNC paths under `\\172.10.18.2\...`) — this is effectively per-job configuration, not just app config. Includes custom coercion (`apply_overrides`/`_coerce_value`) so string overrides (env vars, JSON) get cast to the field's real type (bool/int/float/list/dict).
- `config_store.py` + `app/routes/config.py` (`/config`) — a **runtime settings override UI**: changes made there are persisted to `.app_config_overrides.json` at repo root and reapplied over the `Settings` defaults on next load (`_load_persistent_overrides()` in `settings.py`). This lets operators change job paths/params without editing `.env` or redeploying.
- `app/core/config.py` is a thin backward-compat shim re-exporting `settings`.

### Network path resolution (`app/services/utils/pathing.py`)

Paths in `settings.py` are UNC paths to the file server **by IP** (`\\172.10.18.2\<share>\...`, some written `//172.10.18.2/<share>/...` — both styles are handled), and the app also runs in a Linux Docker container where each share is mounted via CIFS. `resolve_network_path()`/`normalize_path_for_runtime()` detect the runtime (`APP_ENV=docker` or `/.dockerenv`) and rewrite the UNC path to that share's mount point. Any new job reading a network path must go through this helper rather than using the raw path.

The share segment is what makes this work, so it is never dropped:

- `settings.SMB_SHARES` lists every mounted share (`produc`, `Usuarios`, `newfact`) and is the same list `entrypoint.sh` mounts. **A job that reads a new share needs it added there and in `SMB_SHARES` for docker-compose/`.env`.**
- Share names match case-insensitively (settings mixes `Usuarios` and `usuarios`) and resolve to the configured spelling, which is how the mount directory is named.
- `SMB_SERVER` must be the same host the paths use (the IP). `SMB_SERVER_ALIASES` covers the old NetBIOS name (`svrinverpalmas`) in case an operator types it in `/config`.
- The primary share (`SMB_SHARE`) is the only one with its own configurable mount point (`SMB_MOUNT_PATH`); the rest land in `SMB_MOUNT_ROOT/<share>`.
- The CIFS mount needs `nocase` because folder segments vary in case between settings entries (`produc/LD_BCULT` vs `produc/ld_bcult`) — harmless on Windows, fatal on Linux without it.

### DBF reading (`app/services/utils/dbf_reader.py`)

Encodings are tried in order from `settings.DBF_ENCODINGS` (`latin1`, `cp1252`, `utf-8`, `iso-8859-1`) since source DBFs have inconsistent legacy encodings.

### Database access

- `app/core/db.py` — a single global `MySQLConnectionPool` (pool_size=5), used via the `db_connection()` context manager. Don't create ad-hoc connections outside the pool.
- `app/services/queries/pivot_service.py` (dynamic report queries) builds SQL with a **strict whitelist + backtick-quoting**; no user-supplied value is ever interpolated directly into a query. Follow this pattern for any new dynamic/pivot query endpoint.

### FastAPI app assembly (`app/main.py`)

`create_app()` wires: CORS (only `http://localhost:5173` allowed, for the Vite dev server — production serves the built SPA from the same origin), static/assets mounts, `/health` (reports SMB mount readiness), the three routers (`api`, `web`, `config`), and a catch-all `/app/{path:path}` that returns the SPA's `index.html` for client-side routing. The `lifespan` context bootstraps ETL job rows, registers the daily cron jobs and the stale-run sweeper, and starts/stops the APScheduler `BackgroundScheduler` (`America/Bogota` timezone).

### Frontend (`frontend/src/`)

- `App.vue` provides a `toast` function via `provide('toast', fn)`; views consume it with `inject('toast')` — this is the app-wide notification mechanism, not a store.
- `router/index.js` — lazy-loaded routes plus a catch-all 404.
- `composables/useEtlPolling.js` — adaptive polling for run status (4s while a job is active, 20s idle).
- `composables/useFileDownload.js` — binary file download handling for generated CSV/Excel reports.
- `vite.config.js` — `@` alias, dev port, and the `/api` proxy to `:8000`.

## Repository conventions

See [AGENTS.md](AGENTS.md) — currently covers only the `production_pipeline_generator` peak (`pico`) rules folded into "Business rules" above, plus the reminder to run `test_production_pipeline_generator` after changing that logic.
