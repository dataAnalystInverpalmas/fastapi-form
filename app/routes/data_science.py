"""Endpoints de la seccion "Ciencia de datos" (solo lectura sobre la base informes)."""
from __future__ import annotations

import logging
from typing import Callable

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from app.services.data_science.catalog import list_projects
from app.services.data_science.common import FLOR_LABELS
from app.services.data_science.fusarium_risk import fusarium_risk
from app.services.data_science.production_forecast import production_forecast
from app.services.data_science.projection_accuracy import projection_accuracy
from app.services.data_science.quality_anomalies import quality_anomalies

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ds", tags=["ciencia-datos"])

FLOR_PATTERN = "^[A-Z0-9]{3}$"
FINCA_PATTERN = "^[0-9]{3}$"


async def _run(func: Callable, **kwargs):
    try:
        return await run_in_threadpool(func, **kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error en prototipo %s", func.__name__)
        raise HTTPException(status_code=500, detail=f"Error calculando {func.__name__}: {exc}") from exc


@router.get("/proyectos")
def proyectos():
    return {"proyectos": list_projects(), "flores": FLOR_LABELS}


@router.get("/precision-proyecciones")
async def precision_proyecciones(
    flor: str | None = Query(None, pattern=FLOR_PATTERN),
    finca: str | None = Query(None, pattern=FINCA_PATTERN),
):
    return await _run(projection_accuracy, flor=flor, finca=finca)


@router.get("/pronostico-produccion")
async def pronostico_produccion(
    flor: str = Query("CLA", pattern=FLOR_PATTERN),
    finca: str | None = Query(None, pattern=FINCA_PATTERN),
    horizonte: int = Query(12, ge=4, le=26),
):
    return await _run(production_forecast, flor=flor, finca=finca, horizonte=horizonte)


@router.get("/calidad-anomalias")
async def calidad_anomalias(
    flor: str | None = Query(None, pattern=FLOR_PATTERN),
    semanas: int = Query(8, ge=2, le=26),
):
    return await _run(quality_anomalies, flor=flor, semanas=semanas)


@router.get("/riesgo-fusarium")
async def riesgo_fusarium(flor: str | None = Query(None, pattern=FLOR_PATTERN)):
    return await _run(fusarium_risk, flor=flor)
