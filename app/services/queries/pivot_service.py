"""
Servicio de reporte dinámico (tabla pivote) sobre la vista `vw_lonas_pivot`.

== SQL para crear la vista en MySQL ==

    CREATE OR REPLACE VIEW vw_lonas_pivot AS
    SELECT
        dates.año,
        dates.aass,
        ld_lonas.finca,
        ld_lonas.bloque,
        ld_lonas.cosecha,
        ld_lonas.variedad,
        ld_lonas.lonas
    FROM ld_lonas
    INNER JOIN dates ON dates.fecha = DATE(ld_lonas.fecha);

NOTA: La vista expone filas individuales (sin agregar) para que este servicio
      aplique la agregación elegida dinámicamente.
"""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from decimal import Decimal
from typing import Any

from app.core.db import db_connection

# ---------------------------------------------------------------------------
# Whitelists — TODOS los identificadores SQL provienen de estas constantes.
# Nunca se interpolan valores de usuario directamente en la query.
# ---------------------------------------------------------------------------
ALLOWED_FIELDS: frozenset[str] = frozenset(
    {"año", "aass", "finca", "bloque", "cosecha", "variedad"}
)
ALLOWED_METRICS: frozenset[str] = frozenset({"lonas"})
ALLOWED_AGGREGATIONS: frozenset[str] = frozenset(
    {"SUM", "COUNT", "AVG", "MIN", "MAX"}
)
VIEW_NAME = "vw_lonas_pivot"

# ---------------------------------------------------------------------------
# Cache en memoria (LRU simple, máx. 50 entradas)
# ---------------------------------------------------------------------------
_CACHE: OrderedDict[str, Any] = OrderedDict()
_CACHE_MAX = 50


def _cache_key(payload: dict) -> str:
    return hashlib.md5(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _cache_get(key: str) -> Any | None:
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    return None


def _cache_set(key: str, value: Any) -> None:
    _CACHE[key] = value
    _CACHE.move_to_end(key)
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------
def _q(field: str) -> str:
    """Backtick-quote un campo ya validado contra el whitelist."""
    return f"`{field}`"


def _safe_alias(value: Any) -> str:
    """Genera un alias seguro quitando backticks y barras invertidas."""
    return str(value).replace("`", "").replace("\\", "")


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _validate_fields(fields: list[str], allowed: frozenset[str], label: str) -> None:
    invalid = set(fields) - allowed
    if invalid:
        raise ValueError(f"Campos no permitidos en {label}: {sorted(invalid)}")


# Campos por los que se puede filtrar (subconjunto de ALLOWED_FIELDS)
FILTRABLE_FIELDS: frozenset[str] = frozenset({"año", "finca", "variedad"})


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------
def get_filter_options() -> dict[str, list]:
    """Devuelve los valores distintos disponibles para cada campo filtrable."""
    options: dict[str, list] = {}
    with db_connection() as conn:
        cursor = conn.cursor()
        for field in sorted(FILTRABLE_FIELDS):
            cursor.execute(
                f"SELECT DISTINCT {_q(field)} FROM `{VIEW_NAME}` "
                f"ORDER BY {_q(field)}"
            )
            options[field] = [row[0] for row in cursor.fetchall()]
        cursor.close()
    return options


def build_and_run_pivot(
    filas: list[str],
    columnas: list[str],
    valores: list[str],
    agregacion: str,
    filtros: dict[str, list] | None = None,
) -> dict[str, Any]:
    """
    Construye y ejecuta una query dinámica sobre VIEW_NAME.

    Args:
        filas:      Campos para el GROUP BY principal.
        columnas:   Campo pivot (genera columnas dinámicas con CASE WHEN).
                    Se usa sólo el primer elemento. Si está vacío hace GROUP BY simple.
        valores:    Métricas numéricas a agregar.
        agregacion: SUM | COUNT | AVG | MIN | MAX.
        filtros:    {"finca": ["001"], "año": [2025, 2026]} — WHERE campo IN (...).

    Returns:
        {"columns": [...], "data": [[...], ...], "total_rows": int}
    """
    if not filas:
        raise ValueError("Debe seleccionar al menos una fila.")
    if not valores:
        raise ValueError("Debe seleccionar al menos un valor.")

    filtros = filtros or {}
    agregacion = agregacion.upper()
    _validate_fields(filas, ALLOWED_FIELDS, "filas")
    _validate_fields(columnas, ALLOWED_FIELDS, "columnas")
    _validate_fields(valores, ALLOWED_METRICS, "valores")
    _validate_fields(list(filtros.keys()), FILTRABLE_FIELDS, "filtros")
    if agregacion not in ALLOWED_AGGREGATIONS:
        raise ValueError(f"Agregación no permitida: {agregacion!r}")

    # Normalizar filtros: eliminar listas vacías
    filtros_activos = {k: v for k, v in filtros.items() if v}

    key = _cache_key(
        {
            "filas": sorted(filas),
            "columnas": sorted(columnas),
            "valores": sorted(valores),
            "agregacion": agregacion,
            "filtros": {k: sorted(str(x) for x in v) for k, v in filtros_activos.items()},
        }
    )
    cached = _cache_get(key)
    if cached is not None:
        return cached

    with db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        if columnas:
            result = _pivot_query(cursor, filas, columnas, valores, agregacion, filtros_activos)
        else:
            result = _simple_query(cursor, filas, valores, agregacion, filtros_activos)
        cursor.close()

    _cache_set(key, result)
    return result


def clear_cache() -> None:
    """Vacía el caché de resultados."""
    _CACHE.clear()


# ---------------------------------------------------------------------------
# Helpers de filtro WHERE (paramétrico, anti-SQLi)
# ---------------------------------------------------------------------------
def _build_where(filtros: dict[str, list]) -> tuple[str, list]:
    """
    Genera cláusula WHERE con IN parametrizado.
    Los nombres de campo ya fueron validados contra FILTRABLE_FIELDS.
    Los valores se pasan como parámetros %s, nunca interpolados.
    """
    if not filtros:
        return "", []
    clauses: list[str] = []
    params: list[Any] = []
    for field, values in filtros.items():
        placeholders = ", ".join(["%s"] * len(values))
        clauses.append(f"{_q(field)} IN ({placeholders})")
        params.extend(values)
    return "WHERE " + " AND ".join(clauses), params


# ---------------------------------------------------------------------------
# Constructores de query
# ---------------------------------------------------------------------------
def _simple_query(
    cursor,
    filas: list[str],
    valores: list[str],
    agregacion: str,
    filtros: dict[str, list] | None = None,
) -> dict[str, Any]:
    """GROUP BY plano, sin pivote."""
    col_names: list[str] = list(filas)
    select_parts: list[str] = [_q(f) for f in filas]

    for v in valores:
        alias = f"{agregacion}_{v}"
        select_parts.append(f"{agregacion}({_q(v)}) AS `{alias}`")
        col_names.append(alias)

    where_clause, where_params = _build_where(filtros or {})
    group_by = ", ".join(_q(f) for f in filas)
    query = (
        f"SELECT {', '.join(select_parts)} "
        f"FROM `{VIEW_NAME}` "
        f"{where_clause} "
        f"GROUP BY {group_by} "
        f"ORDER BY {group_by}"
    )
    cursor.execute(query, where_params)
    rows = cursor.fetchall()
    data = [[_serialize(row[c]) for c in col_names] for row in rows]
    return {"columns": col_names, "data": data, "total_rows": len(rows)}


def _pivot_query(
    cursor,
    filas: list[str],
    columnas: list[str],
    valores: list[str],
    agregacion: str,
    filtros: dict[str, list] | None = None,
) -> dict[str, Any]:
    """
    GROUP BY sobre `filas` con columnas dinámicas generadas mediante CASE WHEN
    para cada valor distinto de columnas[0].

    Equivalente a:
        SELECT finca,
               SUM(CASE WHEN cosecha = 'C1' THEN lonas END) AS `C1__lonas`,
               SUM(CASE WHEN cosecha = 'C2' THEN lonas END) AS `C2__lonas`
        FROM vw_lonas_pivot
        GROUP BY finca
    """
    pivot_col = columnas[0]  # Solo el primer campo como eje de pivote

    where_clause, where_params = _build_where(filtros or {})

    # Obtener valores distintos del eje pivote (respetando filtros activos)
    cursor.execute(
        f"SELECT DISTINCT {_q(pivot_col)} FROM `{VIEW_NAME}` {where_clause} ORDER BY {_q(pivot_col)}",
        where_params,
    )
    pivot_values: list[Any] = [row[pivot_col] for row in cursor.fetchall()]

    if not pivot_values:
        # Vista vacía: devolver columnas base sin datos
        col_names = list(filas)
        return {"columns": col_names, "data": [], "total_rows": 0}

    # Construir CASE WHEN por cada (pivot_value, metrica)
    case_clauses: list[str] = []
    extra_col_names: list[str] = []
    params: list[Any] = []

    for pv in pivot_values:
        for v in valores:
            alias = f"{_safe_alias(pv)}__{v}"
            case_clauses.append(
                f"{agregacion}(CASE WHEN {_q(pivot_col)} = %s THEN {_q(v)} END) AS `{alias}`"
            )
            extra_col_names.append(alias)
            params.append(pv)  # valor literal, parametrizado con %s

    col_names = list(filas) + extra_col_names
    select_parts = [_q(f) for f in filas] + case_clauses
    group_by = ", ".join(_q(f) for f in filas)

    # IMPORTANTE: en el SQL los %s del CASE WHEN aparecen ANTES que los de WHERE,
    # por lo tanto los params de CASE WHEN van primero.
    all_params = params + where_params
    query = (
        f"SELECT {', '.join(select_parts)} "
        f"FROM `{VIEW_NAME}` "
        f"{where_clause} "
        f"GROUP BY {group_by} "
        f"ORDER BY {group_by}"
    )
    cursor.execute(query, all_params)
    rows = cursor.fetchall()
    data = [[_serialize(row[c]) for c in col_names] for row in rows]
    return {"columns": col_names, "data": data, "total_rows": len(rows)}
