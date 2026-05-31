from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.settings import settings
from app.services.aportes_ponderados_query import exporta_aportes_ponderados_problemas_excel
from app.services.cortes_lonas_query import exporta_cortes_lonas_excel
from app.services.dbf_reader import read_dbf_file
from app.services.etl_params import normalize_job_params, resolve_params_for_run
from app.services.etl_registry import list_jobs as list_jobs_from_catalog
from app.services.etl_repository import (
    get_last_job_params,
    list_jobs_with_state,
    list_recent_runs,
    upsert_last_job_params,
)
from app.services.etl_runner import start_job
from app.services.pivot_service import (
    ALLOWED_AGGREGATIONS,
    ALLOWED_FIELDS,
    ALLOWED_METRICS,
)
from app.services.query_processes import list_query_processes

router = APIRouter()

_ETL_JOBS_EXTRA_IDS = {
    "load_process_guarde",
    "load_process_siembras",
    "load_siembras_teo_real",
}


templates = Jinja2Templates(directory=str(settings.TEMPLATES_DIR))



# Página principal redirige al menú principal (puedes personalizar más adelante)
@router.get("/", response_class=HTMLResponse)
def root(request: Request):
    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
        },
    )



@router.get("/consultar", response_class=HTMLResponse)
def consultar_form(request: Request):
    return templates.TemplateResponse(
        "consultar.html",
        {
            "request": request,
            "data": None,
            "error": None,
            "ruta_archivo": settings.DEFAULT_DBF_PATH,
            "default_path": settings.DEFAULT_DBF_PATH,
            "limite": settings.DEFAULT_LIMIT,
        },
    )

@router.post("/consultar", response_class=HTMLResponse)
def consultar_dbf(
    request: Request,
    ruta_archivo: str = Form(default=settings.DEFAULT_DBF_PATH),
    limite: Optional[int] = Form(default=settings.DEFAULT_LIMIT),
):
    data, error = read_dbf_file(ruta_archivo, limit=limite)
    return templates.TemplateResponse(
        "consultar.html",
        {
            "request": request,
            "data": data,
            "error": error,
            "ruta_archivo": ruta_archivo,
            "default_path": settings.DEFAULT_DBF_PATH,
            "limite": limite,
        },
    )


@router.get("/etl/jobs", response_class=HTMLResponse)
def etl_jobs_page(request: Request):
    status_by_job = {
        str(row.get("job_id", "")): row for row in list_jobs_with_state()
    }
    jobs = []

    for job_def in list_jobs_from_catalog():
        if job_def.job_id.startswith("load_") and job_def.job_id not in _ETL_JOBS_EXTRA_IDS:
            continue

        status_row = status_by_job.get(job_def.job_id)
        if status_row:
            jobs.append(status_row)
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
            }
        )

    jobs.sort(key=lambda item: str(item.get("name", "")).lower())
    return templates.TemplateResponse(
        "etl_jobs.html",
        {
            "request": request,
            "jobs": jobs,
            "mensaje": request.query_params.get("msg"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/etl/params", response_class=HTMLResponse)
def etl_params_page(request: Request):
    status_by_job = {
        str(row.get("job_id", "")): row for row in list_jobs_with_state()
    }

    jobs = []
    for job in list_jobs_from_catalog():
        if not job.supports_params:
            continue

        status = status_by_job.get(job.job_id, {})
        last_params = get_last_job_params(job.job_id)
        defaults = job.default_params or {}

        jobs.append(
            {
                "job_id": job.job_id,
                "name": job.name,
                "description": job.description,
                "menu_type": "load" if job.job_id.startswith("load_") else "etl",
                "default_params": defaults,
                "last_params": last_params,
                "last_status": status.get("last_status") or "",
                "last_started_at": status.get("last_started_at"),
            }
        )

    jobs.sort(key=lambda item: item["name"])
    return templates.TemplateResponse(
        "etl_params.html",
        {
            "request": request,
            "jobs": jobs,
            "mensaje": request.query_params.get("msg"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/etl/params/{job_id}/save")
async def save_etl_job_params(job_id: str, request: Request):
    form = await request.form()
    raw_params: dict[str, str] = {}
    for key, value in form.multi_items():
        if not key.startswith("params__"):
            continue
        param_name = key.replace("params__", "", 1)
        raw_params[param_name] = str(value)

    try:
        params = normalize_job_params(job_id=job_id, raw_params=raw_params)
        upsert_last_job_params(job_id=job_id, params=params)
        return RedirectResponse(url="/etl/params?msg=Parámetros guardados", status_code=303)
    except Exception as exc:  # noqa: BLE001
        return RedirectResponse(url=f"/etl/params?error={exc}", status_code=303)


@router.post("/etl/jobs/{job_id}/run")
def run_etl_job(job_id: str):
    if job_id.startswith("load_"):
        return RedirectResponse(url="/etl/jobs?error=Job no disponible en este menu.", status_code=303)
    try:
        params = resolve_params_for_run(job_id=job_id, raw_params=None)
        start_job(job_id=job_id, triggered_by="web", params=params)
        return RedirectResponse(url="/etl/runs?msg=queued", status_code=303)
    except Exception as exc:  # noqa: BLE001
        return RedirectResponse(url=f"/etl/jobs?error={exc}", status_code=303)


@router.get("/load/jobs", response_class=HTMLResponse)
def load_jobs_page(request: Request):
    jobs = [job for job in list_jobs_with_state() if str(job.get("job_id", "")).startswith("load_") and str(job.get("job_id", "")) not in _ETL_JOBS_EXTRA_IDS]
    return templates.TemplateResponse(
        "load_jobs.html",
        {
            "request": request,
            "jobs": jobs,
            "mensaje": request.query_params.get("msg"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/load/jobs/{job_id}/run")
def run_load_job(job_id: str):
    if not job_id.startswith("load_"):
        return RedirectResponse(url="/load/jobs?error=Job invalido para este menu.", status_code=303)
    try:
        params = resolve_params_for_run(job_id=job_id, raw_params=None)
        start_job(job_id=job_id, triggered_by="web-load", params=params)
        return RedirectResponse(url="/etl/runs?msg=queued", status_code=303)
    except Exception as exc:  # noqa: BLE001
        return RedirectResponse(url=f"/load/jobs?error={exc}", status_code=303)


@router.get("/etl/runs", response_class=HTMLResponse)
def etl_runs_page(request: Request):
    runs = list_recent_runs(limit=100)
    return templates.TemplateResponse(
        "etl_runs.html",
        {
            "request": request,
            "runs": runs,
            "mensaje": request.query_params.get("msg"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/reporte-dinamico", response_class=HTMLResponse)
def reporte_dinamico_page(request: Request):
    return templates.TemplateResponse(
        "reporte_dinamico.html",
        {
            "request": request,
            "campos": sorted(ALLOWED_FIELDS),
            "metricas": sorted(ALLOWED_METRICS),
            "agregaciones": sorted(ALLOWED_AGGREGATIONS),
        },
    )


@router.get("/consultas/procesos", response_class=HTMLResponse)
def consulta_processes_page(request: Request):
    return templates.TemplateResponse(
        "consulta_processes.html",
        {
            "request": request,
            "processes": list_query_processes(),
            "mensaje": request.query_params.get("msg"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/consultas/procesos/exporta-cortes")
def run_exporta_cortes_process(
    fecha_inicio: str = Form(...),
    fecha_fin: str = Form(...),
):
    try:
        output_path = exporta_cortes_lonas_excel(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
    except ValueError as exc:
        return RedirectResponse(url=f"/consultas/procesos?error={exc}", status_code=303)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    filename = Path(output_path).name
    return FileResponse(
        path=output_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/consultas/procesos/aportes-ponderados-problemas")
def run_aportes_ponderados_problemas_process(
    fecha_inicio: str = Form(...),
    fecha_fin: str = Form(...),
):
    try:
        output_path = exporta_aportes_ponderados_problemas_excel(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
    except ValueError as exc:
        return RedirectResponse(url=f"/consultas/procesos?error={exc}", status_code=303)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    filename = Path(output_path).name
    return FileResponse(
        path=output_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

from app.services.tests.test import get_test_endpoint  # noqa: F401
@router.get("/test")
def test_endpoint():
    return get_test_endpoint()