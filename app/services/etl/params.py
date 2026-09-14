from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from app.services.etl.repository import get_last_job_params
from app.services.etl.registry import get_job


def _validate_fecha_range(normalized: dict[str, Any]) -> None:
    """Si el job tiene fecha_inicio y fecha_fin, valida formato y orden cronologico."""
    if "fecha_inicio" not in normalized or "fecha_fin" not in normalized:
        return

    try:
        inicio = datetime.strptime(str(normalized["fecha_inicio"])[:10], "%Y-%m-%d")
        fin = datetime.strptime(str(normalized["fecha_fin"])[:10], "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("fecha_inicio y fecha_fin deben tener formato YYYY-MM-DD.") from exc

    if inicio > fin:
        raise ValueError("fecha_inicio no puede ser mayor que fecha_fin.")


def _split_list_string(value: str) -> list[str]:
    text = str(value).strip()
    if not text:
        return []

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]

    if "\n" in text or "\r" in text:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return [item.strip() for item in normalized.split("\n") if item.strip()]

    separator = ";" if ";" in text else ","
    return [item.strip() for item in text.split(separator) if item.strip()]


def _parse_list(value: Any, sample_item: Any) -> list[Any]:
    if isinstance(value, list):
        items: list[Any] = []
        for item in value:
            if isinstance(item, str):
                items.extend(_split_list_string(item))
            else:
                items.append(item)
    elif isinstance(value, str):
        items = _split_list_string(value)
    else:
        raise ValueError("Debe ser una lista o texto separado por comas, punto y coma o saltos de línea.")

    if isinstance(sample_item, int):
        parsed: list[int] = []
        for item in items:
            if isinstance(item, int):
                parsed.append(item)
                continue
            token = str(item).strip()
            if not token:
                continue
            if not token.lstrip("-").isdigit():
                raise ValueError(f"Valor invalido en lista: '{item}'.")
            parsed.append(int(token))
        return parsed

    if isinstance(sample_item, float):
        parsed_float: list[float] = []
        for item in items:
            try:
                parsed_float.append(float(item))
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"Valor invalido en lista: '{item}'.") from exc
        return parsed_float

    return [str(item) for item in items]


def _coerce_scalar(value: Any, expected: Any) -> Any:
    if isinstance(expected, bool):
        if isinstance(value, bool):
            return value
        token = str(value).strip().lower()
        if token in {"1", "true", "si", "sí", "yes", "y"}:
            return True
        if token in {"0", "false", "no", "n"}:
            return False
        raise ValueError(f"Valor booleano invalido: '{value}'.")

    if isinstance(expected, int):
        if isinstance(value, int):
            return value
        token = str(value).strip()
        if not token or not token.lstrip("-").isdigit():
            raise ValueError(f"Valor entero invalido: '{value}'.")
        return int(token)

    if isinstance(expected, float):
        if isinstance(value, (int, float)):
            return float(value)
        token = str(value).strip()
        if not token:
            raise ValueError("Valor decimal vacio.")
        try:
            return float(token)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Valor decimal invalido: '{value}'.") from exc

    return str(value)


def normalize_job_params(job_id: str, raw_params: dict[str, Any] | None) -> dict[str, Any]:
    job = get_job(job_id)
    if job is None:
        raise ValueError(f"No existe el job '{job_id}'.")

    if not raw_params:
        return {}

    if not job.supports_params:
        # Si el job no soporta params, ignorarlos para evitar bloquear ejecución.
        return {}

    defaults = job.default_params or {}
    allowed_keys = set(defaults.keys())

    unknown = sorted(set(raw_params.keys()) - allowed_keys)
    if unknown:
        raise ValueError(
            f"Parametros no soportados para '{job_id}': " + ", ".join(unknown)
        )

    normalized: dict[str, Any] = {}
    for key in allowed_keys:
        if key not in raw_params:
            continue

        value = raw_params.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue

        expected = defaults[key]

        if isinstance(expected, list):
            sample_item = expected[0] if expected else ""
            parsed = _parse_list(value, sample_item)
            if parsed:
                normalized[key] = parsed
            continue

        normalized[key] = _coerce_scalar(value, expected)

    _validate_fecha_range(normalized)
    return normalized


def resolve_params_for_run(job_id: str, raw_params: dict[str, Any] | None) -> dict[str, Any]:
    """Resuelve parámetros efectivos para ejecutar un job.

    Prioridad:
    1) params enviados explícitamente
    2) últimos params guardados del job
    3) default_params del catálogo
    """
    job = get_job(job_id)
    if job is None:
        raise ValueError(f"No existe el job '{job_id}'.")

    if not job.supports_params:
        return {}

    # Siempre partir de defaults para evitar corridas con params parciales.
    resolved = normalize_job_params(job_id=job_id, raw_params=job.default_params or {})

    last_params = get_last_job_params(job_id)
    normalized_last = normalize_job_params(job_id=job_id, raw_params=last_params)
    if normalized_last:
        resolved.update(normalized_last)

    explicit_params = normalize_job_params(job_id=job_id, raw_params=raw_params)
    if explicit_params:
        resolved.update(explicit_params)

    _validate_fecha_range(resolved)
    return resolved
