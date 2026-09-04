from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.settings import Settings, settings

_CONFIG_FILE = Path(__file__).resolve().parents[2] / ".app_config_overrides.json"


def _normalize_key(key: str) -> str:
    return str(key).strip()


def _group_for_setting(key: str) -> str:
    prefixes = {
        "APP_": "App",
        "DB_": "DB",
        "SMB_": "SMB",
        "LOAD_": "Load",
        "PROYECCIONES_": "Proyecciones",
        "PPROCESADO_": "Producto procesado",
        "PROCESS_": "Procesos",
        "QUIPUS_": "Quipus",
        "PICOS_": "Picos",
        "DIRIGIDAS_": "Dirigidas",
        "PEDIDOS_": "Pedidos",
        "COMPARE_": "Comparativo",
        "ANOMALIAS_": "Anomalías",
        "TABLA_": "Curvas",
        "CURVAS_": "Curvas",
        "CALIDADES_": "Calidades",
        "APORTES_": "Aportes",
        "FUSARIUM_": "Fusarium",
        "PRODUCTIVIDADES_": "Productividades",
        "SIEMBRAS_": "Siembras",
        "ETL_": "ETL",
        "TIMEZONE": "General",
        "BASE_DIR": "General",
        "STATIC_DIR": "General",
        "TEMPLATES_DIR": "General",
        "DEFAULT_": "General",
        "MAX_LIMIT": "General",
        "DBF_": "DBF",
        "PRODUCCION_": "Producción",
    }
    for prefix, group in prefixes.items():
        if key.startswith(prefix):
            return group
    if key in {"APP_NAME", "APP_VERSION", "DEBUG", "APP_ENV"}:
        return "App"
    if key.startswith("DEFAULT"):
        return "General"
    return "General"


def get_setting_groups() -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for key in Settings.model_fields:
        group_name = _group_for_setting(key)
        normalized_group = group_name.lower().replace(" ", "_")
        groups.setdefault(normalized_group, [])
        groups[normalized_group].append(key)

    ordered = {}
    for name in [
        "app",
        "general",
        "db",
        "dbf",
        "smb",
        "proyecciones",
        "producto_procesado",
        "curvas",
        "calidades",
        "aportes",
        "fusarium",
        "productividades",
        "dirigidas",
        "picos",
        "quipus",
        "pedidos",
        "comparativo",
        "anomalias",
        "siembras",
        "procesos",
        "load",
        "produccion",
        "etl",
    ]:
        if name in groups:
            ordered[name] = groups[name]
    for name, values in groups.items():
        if name not in ordered:
            ordered[name] = values
    return ordered


def get_default_settings() -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for key, field in Settings.model_fields.items():
        defaults[key] = field.default
    return defaults


def get_config_overrides() -> dict[str, Any]:
    if not _CONFIG_FILE.exists():
        return {}
    try:
        with _CONFIG_FILE.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_config_overrides(overrides: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in (overrides or {}).items():
        clean_key = _normalize_key(key)
        if not clean_key or clean_key not in Settings.model_fields:
            continue
        normalized[clean_key] = value

    if normalized:
        settings.apply_overrides(normalized)

    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _CONFIG_FILE.open("w", encoding="utf-8") as handle:
        json.dump(normalized, handle, ensure_ascii=False, indent=2)
    return normalized


def clear_config_overrides() -> None:
    settings.reset_to_defaults()
    if _CONFIG_FILE.exists():
        _CONFIG_FILE.unlink()
