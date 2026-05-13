from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.settings import settings
from app.services.dbf_reader import normalize_path
from app.services.etl_helpers import (
    execute_query,
    normalize_finca_series,
    read_many_dbf,
    safe_int_series,
    validate_columns,
)


def _ajustar_a_lunes(fecha: pd.Timestamp) -> pd.Timestamp:
    if pd.isnull(fecha):
        return fecha
    return fecha - pd.Timedelta(days=int(fecha.weekday()))


def _load_proyecciones_dbf() -> pd.DataFrame:
    df_proy = read_many_dbf(settings.PROYECCIONES_BASE_DIR, settings.PROYECCIONES_DBF_FILES)
    if df_proy.empty:
        raise RuntimeError("No se encontraron datos en archivos Proyecciones*.dbf.")

    required = {
        "finca",
        "flor",
        "bloque",
        "nvari",
        "cosecha",
        "fecha",
        "matas",
        "edad",
        "tipo",
        "tallos",
    }
    validate_columns(df_proy, required, "proyecciones*.dbf")

    df_proy = df_proy[
        ["finca", "flor", "bloque", "nvari", "cosecha", "fecha", "matas", "edad", "tipo", "tallos"]
    ].copy()
    df_proy = df_proy.rename(columns={"nvari": "variedad"})
    df_proy["fecha"] = pd.to_datetime(df_proy["fecha"], errors="coerce")

    return df_proy


def _load_db_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sql_pto = f"""
        SELECT
            pto.finca,
            pto.flor,
            pto.bloque,
            pto.variedad,
            pto.cosecha,
            pto.fecha,
            pto.edad,
            c.nombre AS ncolor,
            SUM(pto.tallos) AS tallos,
            SUM(pto.matas) AS matas
        FROM ld_proyeccion_anual AS pto
        LEFT JOIN ld_variedades AS v
            ON v.nombre = pto.variedad
            AND v.codflor = pto.flor
        LEFT JOIN ld_colores AS c
            ON c.codigo = v.codgcol
        WHERE pto.fecha >= '{settings.PROYECCIONES_BUDGET_START_DATE}'
            AND pto.flor IN ({", ".join(f"'{flor}'" for flor in settings.PROYECCIONES_FLOR_FILTER)})
        GROUP BY 1,2,3,4,5,6,7,8
    """

    rows_pto = execute_query(sql_pto) or []
    df_pto = pd.DataFrame(
        rows_pto,
        columns=["finca", "flor", "bloque", "variedad", "cosecha", "fecha", "edad", "ncolor", "tallos", "matas"],
    )

    rows_vari = execute_query(
        """
        SELECT
            v.nombre AS variedad,
            c.nombre AS ncolor
        FROM ld_variedades AS v
        LEFT JOIN ld_colores AS c ON c.codigo = v.codgcol
        """
    ) or []
    df_vari = pd.DataFrame(rows_vari, columns=["variedad", "ncolor"])

    rows_fiestas = execute_query(
        """
        SELECT
            cod_temporada AS cosecha,
            CONCAT(fiesta, RIGHT(YEAR(fecha_pico), 2)) AS ncosecha
        FROM seasons
        """
    ) or []
    df_fiestas = pd.DataFrame(rows_fiestas, columns=["cosecha", "ncosecha"])

    return df_pto, df_vari, df_fiestas


def generate_proyecciones_csv() -> str:
    df_proy = _load_proyecciones_dbf()
    df_pto, df_vari, df_fiestas = _load_db_data()

    df_proy = pd.merge(df_proy, df_vari, how="left", on="variedad")

    if not df_pto.empty:
        df_pto["tipo"] = "PT"
        df_pto = df_pto[["finca", "flor", "bloque", "variedad", "cosecha", "fecha", "matas", "edad", "tipo", "ncolor", "tallos"]]

    df = pd.concat([df_proy, df_pto], ignore_index=True)

    if df.empty:
        raise RuntimeError("No hay datos para generar proyecciones.csv.")

    df["matas"] = safe_int_series(df["matas"])
    df["tallos"] = safe_int_series(df["tallos"])
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.normalize()
    df = df[df["fecha"].notna()].copy()
    df["fecha"] = df["fecha"].apply(_ajustar_a_lunes)

    for col in ["finca", "flor", "variedad", "cosecha", "tipo", "ncolor"]:
        df[col] = df[col].astype(str).str.strip()

    # Asegurar finca en formato texto consistente (001/002/...).
    df["finca"] = normalize_finca_series(df["finca"])

    df_final = (
        df.groupby(
            ["finca", "flor", "bloque", "variedad", "cosecha", "fecha", "matas", "edad", "ncolor", "tipo"],
            dropna=False,
        )["tallos"]
        .sum()
        .reset_index()
    )

    df_final = pd.merge(df_final, df_fiestas, on="cosecha", how="left")

    output_path = Path(normalize_path(settings.PROYECCIONES_OUTPUT_PATH))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_final.to_csv(output_path, index=False)

    return str(output_path)
