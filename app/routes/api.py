from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi.responses import FileResponse
from mysql.connector import Error as MySQLError

from app.services.utils.dbf_reader import read_dbf_file
from app.services.etl.params import normalize_job_params, resolve_params_for_run
from app.services.etl.repository import (
    count_by_status,
    get_last_job_params,
    list_jobs_with_state,
    list_recent_runs,
    upsert_last_job_params,
)
from app.services.etl.registry import list_jobs as list_jobs_from_catalog
from app.services.etl.runner import start_job
from pydantic import BaseModel, field_validator

from app.services.queries.aportes_ponderados_query import exporta_aportes_ponderados_problemas_excel
from app.services.queries.cortes_lonas_query import exporta_cortes_lonas_excel
from app.services.etl.constants import ETL_LOAD_EXTRA_IDS

from app.services.queries.pivot_service import (
    ALLOWED_AGGREGATIONS,
    ALLOWED_FIELDS,
    ALLOWED_METRICS,
    build_and_run_pivot,
    clear_cache as pivot_clear_cache,
    get_filter_options,
)


router = APIRouter(prefix="/api")


class PivotRequest(BaseModel):
    filas: list[str]
    columnas: list[str] = []
    valores: list[str]
    agregacion: str = "SUM"
    filtros: dict[str, list] = {}

    @field_validator("filas", "columnas", "valores", mode="before")
    @classmethod
    def _no_empty_strings(cls, v: list) -> list:
        return [item for item in v if item]

    @field_validator("agregacion", mode="before")
    @classmethod
    def _upper_agg(cls, v: str) -> str:
        return v.upper()


class RunJobRequest(BaseModel):
    params: dict[str, Any] | None = None


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convierte datetimes a ISO-string para serialización JSON."""
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}


@router.get("/dbf/{ruta:path}")
def api_consultar_dbf(ruta: str, limit: Optional[int] = 100):
    data, error = read_dbf_file(ruta, limit=limit)
    if error:
        return {"error": error}
    return data


@router.get("/etl/kpis")
def api_etl_kpis():
    return count_by_status()


@router.get("/etl/jobs")
def api_list_etl_jobs():
    catalog = {job.job_id: job for job in list_jobs_from_catalog()}
    status_by_job = {
        str(row.get("job_id", "")): row for row in list_jobs_with_state()
    }

    jobs = []
    for job_def in list_jobs_from_catalog():
        if job_def.job_id.startswith("load_") and job_def.job_id not in ETL_LOAD_EXTRA_IDS:
            continue

        status_row = status_by_job.get(job_def.job_id)
        if status_row:
            jobs.append(
                {
                    **_serialize_row(status_row),
                    "supports_params": bool(job_def.supports_params),
                    "default_params": job_def.default_params or {},
                }
            )
            continue

        jobs.append(
            {
                "job_id": job_def.job_id,
                "name": job_def.name,
                "description": job_def.description,
                "allows_parallel": 1 if job_def.allows_parallel else 0,
                "timeout_seconds": job_def.timeout_seconds,
                "is_active": 1,
                "updated_at": None,
                "last_status": None,
                "last_started_at": None,
                "supports_params": bool(job_def.supports_params),
                "default_params": job_def.default_params or {},
            }
        )

    jobs.sort(key=lambda item: str(item.get("name", "")).lower())
    return jobs


@router.get("/load/jobs")
def api_list_load_jobs():
    jobs = [
        _serialize_row(job)
        for job in list_jobs_with_state()
        if str(job.get("job_id", "")).startswith("load_") and str(job.get("job_id", "")) not in ETL_LOAD_EXTRA_IDS
    ]
    return jobs


@router.get("/etl/runs")
def api_list_runs():
    runs = [_serialize_row(run) for run in list_recent_runs(limit=100)]
    return runs


@router.post("/etl/jobs/{job_id}/run")
def api_run_job(job_id: str, payload: RunJobRequest | None = None):
    try:
        params = resolve_params_for_run(job_id=job_id, raw_params=payload.params if payload else None)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        run_id = start_job(job_id=job_id, triggered_by="api", params=params)
        return {
            "ok": True,
            "job_id": job_id,
            "run_id": run_id,
            "status": "queued",
            "params": params,
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/etl/jobs/{job_id}/last-params")
def api_last_job_params(job_id: str):
    return {"job_id": job_id, "params": get_last_job_params(job_id)}


@router.get("/reporte-dinamico/filtros")
def api_pivot_filtros():
    try:
        options = get_filter_options()
        # Agrega también los campos, métricas y agregaciones disponibles
        # para que el frontend Vue no dependa de datos pasados por Jinja2
        return {
            **options,
            "campos": sorted(ALLOWED_FIELDS),
            "metricas": sorted(ALLOWED_METRICS),
            "agregaciones": sorted(ALLOWED_AGGREGATIONS),
        }
    except MySQLError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error de base de datos: {exc.msg if hasattr(exc, 'msg') else str(exc)}",
        ) from exc


@router.post("/reporte-dinamico")
def api_reporte_dinamico(payload: PivotRequest):
    try:
        result = build_and_run_pivot(
            filas=payload.filas,
            columnas=payload.columnas,
            valores=payload.valores,
            agregacion=payload.agregacion,
            filtros=payload.filtros,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MySQLError as exc:
        # Devuelve JSON consistente para que el frontend no intente parsear texto plano.
        raise HTTPException(
            status_code=500,
            detail=f"Error de base de datos: {exc.msg if hasattr(exc, 'msg') else str(exc)}",
        ) from exc


@router.post("/reporte-dinamico/cache/clear")
def api_clear_pivot_cache():
    pivot_clear_cache()
    return {"ok": True, "message": "Caché del reporte dinámico vaciado."}


# ── ETL Params ───────────────────────────────────────────────────────────────

class SaveParamsRequest(BaseModel):
    params: dict[str, Any]


@router.get("/etl/params")
def api_list_etl_params():
    """Lista todos los jobs que soportan parámetros con sus valores actuales."""
    catalog = {job.job_id: job for job in list_jobs_from_catalog() if job.supports_params}
    status_by_job = {str(r.get("job_id", "")): r for r in list_jobs_with_state()}

    jobs = []
    for job_id, job in catalog.items():
        status = status_by_job.get(job_id, {})
        last_params = get_last_job_params(job_id)
        jobs.append(
            {
                "job_id": job_id,
                "name": job.name,
                "description": job.description,
                "menu_type": "load" if job_id.startswith("load_") else "etl",
                "default_params": job.default_params or {},
                "last_params": last_params,
                "last_status": status.get("last_status") or "",
                "last_started_at": status.get("last_started_at"),
            }
        )
    jobs.sort(key=lambda j: j["name"])
    return jobs


@router.post("/etl/params/{job_id}/save")
def api_save_etl_params(job_id: str, payload: SaveParamsRequest):
    """Guarda parámetros de un job ETL."""
    try:
        # Procesar valores: mantener listas como tales, convertir otros a string
        raw_params = {}
        for k, v in payload.params.items():
            if isinstance(v, list):
                raw_params[k] = v
            else:
                raw_params[k] = str(v)
        
        params = normalize_job_params(job_id=job_id, raw_params=raw_params)
        upsert_last_job_params(job_id=job_id, params=params)
        return {"ok": True, "job_id": job_id, "params": params}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Consultas / Exportaciones Excel ──────────────────────────────────────────

class FechasRequest(BaseModel):
    fecha_inicio: str
    fecha_fin: str


@router.post("/consultas/exporta-cortes")
def api_exporta_cortes(payload: FechasRequest):
    """Genera el Excel de cortes de lonas y lo devuelve como descarga."""
    try:
        output_path = exporta_cortes_lonas_excel(
            fecha_inicio=payload.fecha_inicio, fecha_fin=payload.fecha_fin
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    filename = Path(output_path).name
    return FileResponse(
        path=output_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/consultas/aportes-ponderados")
def api_aportes_ponderados(payload: FechasRequest):
    """Genera el Excel de aportes ponderados con problemas y lo devuelve como descarga."""
    try:
        output_path = exporta_aportes_ponderados_problemas_excel(
            fecha_inicio=payload.fecha_inicio, fecha_fin=payload.fecha_fin
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    filename = Path(output_path).name
    return FileResponse(
        path=output_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


