from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.db import db_connection
from app.core.settings import settings
from app.services.dbf_reader import normalize_path
from app.services.etl_helpers import normalize_finca_series, resolve_date_range_params


ALL_FARMS_CODE = "000"


FUSARIUM_BASE_QUERY = """
    SELECT
        fecha,
        finca,
        nvari AS variedad,
        pico AS ciclo,
        AVG(porc) AS fusarium
    FROM ld_fusarium
    WHERE fecha BETWEEN %s AND %s
    GROUP BY fecha, finca, variedad, ciclo
"""


def _load_fusarium_rows(fecha_inicio: pd.Timestamp, fecha_fin: pd.Timestamp) -> pd.DataFrame:
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            FUSARIUM_BASE_QUERY,
            (fecha_inicio.strftime("%Y-%m-%d"), fecha_fin.strftime("%Y-%m-%d")),
        )
        rows = cursor.fetchall()
        cursor.close()

    df_fusarium = pd.DataFrame(rows, columns=["fecha", "finca", "variedad", "ciclo", "fusarium"])
    if df_fusarium.empty:
        raise RuntimeError(
            f"No hay datos de fusarium entre {fecha_inicio.strftime('%Y-%m-%d')} y {fecha_fin.strftime('%Y-%m-%d')} para procesar."
        )

    df_fusarium["fecha"] = pd.to_datetime(df_fusarium["fecha"], errors="coerce").dt.normalize()
    df_fusarium["finca"] = normalize_finca_series(df_fusarium["finca"])
    df_fusarium["variedad"] = df_fusarium["variedad"].astype(str).str.strip()
    df_fusarium["ciclo"] = pd.to_numeric(df_fusarium["ciclo"], errors="coerce").astype("Int64")
    df_fusarium["fusarium"] = pd.to_numeric(df_fusarium["fusarium"], errors="coerce")
    df_fusarium = df_fusarium.dropna(subset=["fecha", "ciclo", "fusarium"]).copy()
    if df_fusarium.empty:
        raise RuntimeError("No quedaron registros válidos de fusarium después de normalizar fechas, ciclo y porcentaje.")

    return df_fusarium


def _build_fusarium_export(df_fusarium: pd.DataFrame) -> pd.DataFrame:
    df_export = (
        df_fusarium.groupby(["finca", "variedad", "ciclo"], as_index=False)["fusarium"]
        .mean()
    )
    df_all_farms = (
        df_fusarium.groupby(["variedad", "ciclo"], as_index=False)["fusarium"]
        .mean()
    )
    df_all_farms["finca"] = ALL_FARMS_CODE
    df_all_farms = df_all_farms[["finca", "variedad", "ciclo", "fusarium"]]
    df_export = (
        pd.concat([df_export, df_all_farms], ignore_index=True)
        .sort_values(["finca", "variedad", "ciclo"], kind="stable")
        .reset_index(drop=True)
    )
    df_export["fusarium"] = df_export["fusarium"].round(4)
    return df_export


def _generate_fusarium_export(fecha_inicio: pd.Timestamp, fecha_fin: pd.Timestamp) -> str:
    df_fusarium = _load_fusarium_rows(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
    df_export = _build_fusarium_export(df_fusarium)

    output_path = Path(normalize_path(settings.FUSARIUM_VARIETIES_OUTPUT_PATH))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_export.to_csv(output_path, index=False, encoding="utf-8-sig")
    return str(output_path)


def generate_fusarium_pipeline(params: dict | None = None) -> str:
    fecha_inicio, fecha_fin = resolve_date_range_params(params)
    output_path = _generate_fusarium_export(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
    return f"csv:{output_path}"