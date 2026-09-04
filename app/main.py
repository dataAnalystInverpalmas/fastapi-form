from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.settings import settings
from app.routes.web import router as web_router
from app.routes.api import router as api_router
from app.routes.config import router as config_router
from app.services.etl.runner import bootstrap_jobs, start_job
from app.services.etl.repository import fail_all_stale_runs
from app.services.utils.network_health import ensure_mount_ready


_BOGOTA_TZ = "America/Bogota"
_scheduler = BackgroundScheduler(timezone=_BOGOTA_TZ)

_DAILY_JOBS = [
    "load_maestra_lonas",
    "load_tabla_descarta_curva",
    "load_tabla_metas",
    "load_tabla_nacional",
    "bajas_exportado",
]


def _schedule_daily_job(job_id: str) -> None:
    def _runner() -> None:
        try:
            start_job(job_id, triggered_by="scheduler")
        except RuntimeError:
            # Ya hay una corrida en progreso; se omite esta ejecución
            pass

    _scheduler.add_job(
        _runner,
        CronTrigger(hour=10, minute=0, timezone=_BOGOTA_TZ),
        id=f"{job_id}_daily",
        replace_existing=True,
    )


def _schedule_stale_runs_sweeper() -> None:
    _scheduler.add_job(
        fail_all_stale_runs,
        IntervalTrigger(minutes=1, timezone=_BOGOTA_TZ),
        id="etl_stale_runs_sweeper",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

# Directorio del build de Vite
_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


@asynccontextmanager
async def _lifespan(app: FastAPI):
    bootstrap_jobs()
    for _job_id in _DAILY_JOBS:
        _schedule_daily_job(_job_id)
    _schedule_stale_runs_sweeper()
    _scheduler.start()
    yield
    _scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=_lifespan,
    )

    # CORS: permite el dev server de Vite en http://localhost:5173
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")

    # Servir assets del build de Vite si el directorio existe
    if (_FRONTEND_DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="frontend-assets")

    @app.get("/health", include_in_schema=False)
    async def health_check() -> dict[str, object]:
        ok, message = ensure_mount_ready()
        return {"status": "ok" if ok else "degraded", "message": message, "app_env": settings.APP_ENV}

    app.include_router(api_router)
    app.include_router(web_router)
    app.include_router(config_router)

    # SPA catch-all: sirve index.html del build de Vite para rutas no-API
    _index = _FRONTEND_DIST / "index.html"

    @app.get("/app/{path:path}", include_in_schema=False)
    async def spa_catch_all(path: str) -> FileResponse:
        return FileResponse(str(_index))

    return app


app = create_app()

