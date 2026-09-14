from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.core.config_store import (
    clear_config_overrides,
    get_config_overrides,
    get_default_settings,
    get_setting_groups,
    save_config_overrides,
)
from app.core.settings import settings

router = APIRouter(prefix="/api/config")


@router.get("/groups")
def list_config_groups() -> dict[str, list[str]]:
    return get_setting_groups()


@router.get("/values")
def list_config_values() -> dict[str, Any]:
    """Config completa para la pantalla de administracion (frontend Vue):
    grupos, valores actuales, defaults de fabrica y overrides activos."""
    groups = get_setting_groups()
    values = {key: getattr(settings, key) for keys in groups.values() for key in keys}
    return {
        "groups": groups,
        "values": values,
        "defaults": get_default_settings(),
        "overrides": get_config_overrides(),
    }


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
