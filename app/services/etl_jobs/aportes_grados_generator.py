from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.db import db_connection
from app.core.settings import settings
from app.services.dbf_reader import normalize_path
from app.services.etl_helpers import normalize_finca_series, resolve_date_range_params, safe_int_series


# ---------------------------------------------------------------------------
# Consulta base a ld_producto_procesado
# ---------------------------------------------------------------------------

PROCESADO_QUERY = """
SELECT
    fecha, flor, finca, bloque, nvari,
    CASE
        WHEN fuente IN ('Clasificacion') THEN 'procesado'
        WHEN fuente IN ('Dirigida', 'AjFito Cultivo') THEN 'dirigida_cultivo'
        WHEN fuente IN ('Dirigida Finca-Flor-Variedad', 'AjFito Cultivo DFFV') THEN 'dirigida_pc'
    END AS fuente,
    grado,
    SUM(tallos) AS tallos
FROM ld_producto_procesado
WHERE fecha BETWEEN %s AND %s
  AND fuente IN (
      'Clasificacion',
      'Dirigida', 'AjFito Cultivo',
      'Dirigida Finca-Flor-Variedad', 'AjFito Cultivo DFFV'
  )
GROUP BY fecha, flor, finca, bloque, nvari, fuente, grado
"""

DATES_QUERY = """
SELECT fecha, aass FROM dates WHERE fecha BETWEEN %s AND %s
"""


# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------

def _load_procesado(fecha_inicio: pd.Timestamp, fecha_fin: pd.Timestamp) -> pd.DataFrame:
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            PROCESADO_QUERY,
            (fecha_inicio.strftime("%Y-%m-%d"), fecha_fin.strftime("%Y-%m-%d")),
        )
        rows = cursor.fetchall()
        cursor.close()

    if not rows:
        raise RuntimeError(
            f"No hay datos en ld_producto_procesado entre "
            f"{fecha_inicio.strftime('%Y-%m-%d')} y {fecha_fin.strftime('%Y-%m-%d')}."
        )

    df = pd.DataFrame(rows, columns=["fecha", "flor", "finca", "bloque", "nvari", "fuente", "grado", "tallos"])
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.normalize()
    df["finca"] = normalize_finca_series(df["finca"])
    df["bloque"] = df["bloque"].astype(str).str.strip()
    df["flor"] = df["flor"].astype(str).str.strip()
    df["nvari"] = df["nvari"].astype(str).str.strip()
    df["grado"] = df["grado"].astype(str).str.strip()
    df["tallos"] = pd.to_numeric(df["tallos"], errors="coerce").fillna(0)
    df = df.dropna(subset=["fecha"]).copy()
    return df


def _load_dates(fecha_inicio: pd.Timestamp, fecha_fin: pd.Timestamp) -> pd.DataFrame:
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            DATES_QUERY,
            (fecha_inicio.strftime("%Y-%m-%d"), fecha_fin.strftime("%Y-%m-%d")),
        )
        rows = cursor.fetchall()
        cursor.close()

    df_dates = pd.DataFrame(rows, columns=["fecha", "aass"])
    df_dates["fecha"] = pd.to_datetime(df_dates["fecha"], errors="coerce").dt.normalize()
    df_dates["aass"] = safe_int_series(df_dates["aass"]).astype(int)
    df_dates = df_dates.dropna(subset=["fecha"]).drop_duplicates(subset=["fecha"]).copy()
    return df_dates


# ---------------------------------------------------------------------------
# Transformación
# ---------------------------------------------------------------------------

def _build_aportes_export(df: pd.DataFrame, df_dates: pd.DataFrame) -> pd.DataFrame:
    df = df[df["grado"] != "CB"].copy()
    df = pd.merge(df, df_dates[["fecha", "aass"]], on="fecha", how="left")
    df = df.dropna(subset=["aass"]).copy()
    df["aass"] = df["aass"].astype(int)

    GROUP_KEYS = ["aass", "finca", "flor", "bloque", "nvari", "fuente", "grado"]
    df_grouped = (
        df.groupby(GROUP_KEYS, as_index=False)["tallos"]
        .sum()
    )

    PARTITION_KEYS = ["aass", "finca", "flor", "bloque", "nvari", "fuente"]
    df_grouped["aporte"] = (
        df_grouped.groupby(PARTITION_KEYS)["tallos"]
        .transform(lambda s: s / s.sum())
    )

    df_grouped["aporte"] = df_grouped["aporte"].round(6)
    df_grouped = df_grouped.sort_values(GROUP_KEYS, kind="stable").reset_index(drop=True)
    return df_grouped


# ---------------------------------------------------------------------------
# Runner principal
# ---------------------------------------------------------------------------

def _generate_aportes_grados(fecha_inicio: pd.Timestamp, fecha_fin: pd.Timestamp) -> str:
    df_procesado = _load_procesado(fecha_inicio, fecha_fin)
    df_dates = _load_dates(fecha_inicio, fecha_fin)

    df_export = _build_aportes_export(df_procesado, df_dates)
    if df_export.empty:
        raise RuntimeError("No quedaron registros después de cruzar con la tabla de fechas.")

    output_path = Path(normalize_path(settings.APORTES_GRADOS_OUTPUT_PATH))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_export.to_csv(output_path, index=False, encoding="utf-8-sig")
    return str(output_path)


def generate_aportes_grados(params: dict | None = None) -> str:
    fecha_inicio, fecha_fin = resolve_date_range_params(params)
    output_path = _generate_aportes_grados(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
    return f"csv:{output_path}"
