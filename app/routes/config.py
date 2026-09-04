from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.config_store import (
    clear_config_overrides,
    get_config_overrides,
    get_default_settings,
    get_setting_groups,
    save_config_overrides,
)
from app.core.settings import settings

router = APIRouter(prefix="/config")
templates = Jinja2Templates(directory=str(settings.TEMPLATES_DIR))


@router.get("", response_class=HTMLResponse)
def config_page(request: Request):
    groups = get_setting_groups()
    defaults = get_default_settings()
    current = get_config_overrides()
    values_by_group = {
        group: {key: getattr(settings, key) for key in keys}
        for group, keys in groups.items()
    }
    return templates.TemplateResponse(
        "configuracion.html",
        {
            "request": request,
            "groups": groups,
            "settings_by_group": values_by_group,
            "default_values": defaults,
            "current_overrides": current,
        },
    )


@router.get("/groups")
def list_config_groups() -> dict[str, list[str]]:
    return get_setting_groups()


@router.get("/values")
def list_config_values() -> dict[str, Any]:
    values = {}
    for group, keys in get_setting_groups().items():
        values[group] = {key: getattr(settings, key) for key in keys}
    return values


@router.post("/save")
def save_config(payload: dict[str, Any]):
    try:
        overrides = save_config_overrides(payload or {})
        return {"ok": True, "saved": overrides}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/reset")
def reset_config():
    try:
        clear_config_overrides()
        return {"ok": True, "message": "Configuración restaurada a valores por defecto."}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
