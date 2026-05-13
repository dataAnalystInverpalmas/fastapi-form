from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.settings import settings
from app.routes.web import router as web_router
from app.routes.api import router as api_router
from app.services.etl_runner import bootstrap_jobs

# Directorio del build de Vite
_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
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

    app.include_router(api_router)
    app.include_router(web_router)

    @app.on_event("startup")
    def on_startup() -> None:
        # Ensure ETL metadata tables and base catalog are ready.
        bootstrap_jobs()

    # SPA catch-all: sirve index.html del build de Vite para rutas no-API
    _index = _FRONTEND_DIST / "index.html"

    @app.get("/app/{path:path}", include_in_schema=False)
    async def spa_catch_all(path: str) -> FileResponse:
        return FileResponse(str(_index))

    return app


app = create_app()

