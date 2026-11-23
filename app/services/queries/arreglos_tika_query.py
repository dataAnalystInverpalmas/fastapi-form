from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.db import db_connection
from app.core.settings import settings
from app.services.queries.cortes_lonas_query import (
    MAX_FILAS_POR_ARCHIVO,
    _escribir_en_partes,
    formato_tika,
    mapear_finca,
)
from app.services.utils.dbf_reader import normalize_path


def preparar_arreglos_tika(df: pd.DataFrame) -> pd.DataFrame:
    """Lleva filas de ld_arre (finca/bloque/variedad/tipo/cantidad) al formato Tika."""
    df = df.copy()
    df["finca"] = mapear_finca(df["finca"])
    return formato_tika(df)


def exporta_arreglos_tika_excel(
    fecha_inicio: str,
    fecha_fin: str,
    flores: list[str] | None = None,
    nombre_archivo: str = "ExportaArreglosTika",
    max_filas: int = MAX_FILAS_POR_ARCHIVO,
) -> list[str]:
    try:
        ini = pd.to_datetime(fecha_inicio, errors="raise").normalize()
        fin = pd.to_datetime(fecha_fin, errors="raise").normalize()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Fechas invalidas. Usa formato YYYY-MM-DD.") from exc
    if ini > fin:
        raise ValueError("fecha_inicio no puede ser mayor que fecha_fin.")

    flores = [str(f).strip().upper() for f in (flores if flores is not None else settings.ARREGLOS_TIKA_FLOR_FILTER)]
    if not flores:
        raise ValueError("No hay codigos de flor configurados para exportar arreglos.")
    placeholders = ", ".join(["%s"] * len(flores))

    # ld_arre trae el codigo en `variedad` y el nombre en `nombre_variedad` (ver load_arre_generator).
    sql = f"""
        SELECT
            a.finca,
            a.bloque,
            COALESCE(NULLIF(TRIM(a.nombre_variedad), ''), a.variedad) AS variedad,
            a.tipo,
            SUM(COALESCE(a.tallos, 0)) AS cantidad
        FROM ld_arre AS a
        WHERE DATE(a.fecha) BETWEEN %s AND %s
          AND UPPER(TRIM(a.flor)) IN ({placeholders})
        GROUP BY a.finca, a.bloque, COALESCE(NULLIF(TRIM(a.nombre_variedad), ''), a.variedad), a.tipo
    """

    with db_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(sql, (ini.date(), fin.date(), *flores))
        rows = cursor.fetchall()
        cursor.close()

    df = pd.DataFrame(rows, columns=["finca", "bloque", "variedad", "tipo", "cantidad"])
    df = preparar_arreglos_tika(df)

    output_dir = Path(normalize_path(settings.EXCEL_OUTPUT_DIR))
    output_dir.mkdir(parents=True, exist_ok=True)

    base = f"processed_arreglos_{nombre_archivo}_{ini.strftime('%Y%m%d')}_{fin.strftime('%Y%m%d')}"
    return [str(p) for p in _escribir_en_partes(df, output_dir, base, max_filas)]


def generate_arreglos_tika(params: dict | None = None) -> str:
    params = params or {}
    output_paths = exporta_arreglos_tika_excel(
        fecha_inicio=params.get("fecha_inicio"),
        fecha_fin=params.get("fecha_fin"),
    )
    return " | ".join(f"xlsx:{path}" for path in output_paths)
