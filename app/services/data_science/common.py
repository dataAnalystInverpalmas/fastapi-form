"""Utilidades compartidas por los prototipos de ciencia de datos."""
from __future__ import annotations

import math
import threading
import time
import warnings
from functools import wraps
from typing import Any, Callable

import pandas as pd

from app.core.db import db_connection

# Las tablas fuente se recargan una vez al dia; 15 minutos de cache evita
# recalcular agregados sobre millones de filas en cada visita a la pagina.
CACHE_TTL_SECONDS = 15 * 60

FLOR_LABELS = {
    "CLA": "Clavel",
    "CM0": "Mini clavel",
    "ROC": "Rosa (cultivo)",
    "ROS": "Rosa",
    "VCL": "Esqueje clavel",
    "VCM": "Esqueje mini clavel",
    "VRC": "Esqueje rosa",
}


def read_sql(sql: str, params: tuple | list | None = None) -> pd.DataFrame:
    with db_connection() as connection, warnings.catch_warnings():
        # pandas advierte cuando recibe una conexion DBAPI que no es SQLAlchemy.
        warnings.simplefilter("ignore", UserWarning)
        return pd.read_sql(sql, connection, params=params)


def ttl_cache(seconds: int = CACHE_TTL_SECONDS) -> Callable:
    def decorator(func: Callable) -> Callable:
        store: dict[tuple, tuple[float, Any]] = {}
        lock = threading.Lock()

        @wraps(func)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.monotonic()
            with lock:
                hit = store.get(key)
                if hit and now - hit[0] < seconds:
                    return hit[1]
            value = func(*args, **kwargs)
            with lock:
                store[key] = (now, value)
            return value

        wrapper.cache_clear = store.clear  # type: ignore[attr-defined]
        return wrapper

    return decorator


def clean_number(value: Any, digits: int = 4) -> Any:
    """Convierte NaN/inf a None y redondea para que el JSON sea valido y compacto."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, digits)


def records(df: pd.DataFrame, digits: int = 4) -> list[dict[str, Any]]:
    out = []
    for row in df.to_dict(orient="records"):
        clean = {}
        for key, value in row.items():
            if hasattr(value, "isoformat"):
                clean[key] = value.isoformat()[:10]
            elif isinstance(value, (int, float)) or value is None:
                clean[key] = clean_number(value, digits)
            else:
                clean[key] = value
        out.append(clean)
    return out
