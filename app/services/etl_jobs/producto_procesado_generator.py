from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from app.core.settings import settings
from app.services.utils.dbf_reader import normalize_path
from app.services.etl.helpers import (
    dataframe_to_sql,
    execute_query,
    read_dbf,
    safe_int_series,
    validate_columns,
)


def _build_variedades_catalog() -> pd.DataFrame:
    rows = execute_query("SELECT codigo, nombre FROM ld_variedades") or []
    df_vari = pd.DataFrame(rows, columns=["variedad", "nvari"])
    if df_vari.empty:
        raise RuntimeError("No se encontraron datos en ld_variedades para enriquecer nvari.")

    df_vari["variedad"] = df_vari["variedad"].astype(str).str.strip()
    df_vari["nvari"] = df_vari["nvari"].astype(str).str.strip()
    return df_vari.drop_duplicates(subset=["variedad"], keep="first")


def _asignar_grado(df: pd.DataFrame) -> pd.DataFrame:

    df = df.copy()

    df["grado"] = np.where(
        df["grado"].isin(["SEL", "080", "070", "090", "100"]),
        "SEL",
        np.where(
            df["grado"].isin(["FAN", "060"]),
            "FAN",
            np.where(
                df["grado"].isin(["STD", "050"]),
                "STD",
                np.where(
                    df["grado"].isin(["SHR", "040", "030"]),
                    "SHR",
                    df["grado"],
                ),
            ),
        ),
    )

    return df


def generate_producto_procesado_csv() -> str:

    pprocesado_2024 = read_dbf(settings.PPROCESADO_2024_PATH)
    pprocesado_2025 = read_dbf(settings.PPROCESADO_2025_PATH)
    pprocesado = read_dbf(settings.PPROCESADO_CURRENT_PATH)

    required_columns = {"flor", "tallos", "ano", "fuente", "grado", "fecha", "finca", "bloque", "variedad"}
    for nombre, df in [("pprocesado_2024", pprocesado_2024), ("pprocesado_2025", pprocesado_2025), ("pprocesado", pprocesado)]:
        validate_columns(df, required_columns, nombre)

    filtro_flor = settings.PPROCESADO_FLOR_FILTER
    filtro_fuente = settings.PPROCESADO_FUENTE_FILTER

    df_2024 = pprocesado_2024[
        (pprocesado_2024["flor"].isin(filtro_flor))
        & (pprocesado_2024["tallos"] != 0)
        & (pprocesado_2024["ano"] == 2024)
        & (pprocesado_2024["fuente"].isin(filtro_fuente))
    ]

    df_2025 = pprocesado[
        (pprocesado["flor"].isin(filtro_flor))
        & (pprocesado["tallos"] != 0)
        & (pprocesado["ano"] == 2025)
        & (pprocesado["fuente"].isin(filtro_fuente))
    ]

    df_2026 = pprocesado[
        (pprocesado["flor"].isin(filtro_flor))
        & (pprocesado["tallos"] != 0)
        & (pprocesado["ano"] >= 2026)
        & (pprocesado["fuente"].isin(filtro_fuente))
    ]

    df_2024 = _asignar_grado(df_2024)
    df_2025 = _asignar_grado(df_2025)
    df_2026 = _asignar_grado(df_2026)

    df_final = pd.concat([df_2024, df_2025, df_2026], ignore_index=True)

    df_final = df_final[
        [
            "finca",
            "bloque",
            "variedad",
            "grado",
            "tallos",
            "fecha",
            "fuente",
            "flor",
        ]
    ]

    df_final["tallos"] = safe_int_series(df_final["tallos"]).astype(int)
    df_final["fecha"] = pd.to_datetime(df_final["fecha"])
    df_final["variedad"] = df_final["variedad"].astype(str).str.strip()

    df_vari = _build_variedades_catalog()
    df_export = pd.merge(df_final, df_vari, how="left", on="variedad")
    df_export["nvari"] = df_export["nvari"].fillna(df_export["variedad"])
    df_export = df_export[["finca", "bloque", "nvari", "grado", "tallos", "fecha", "fuente", "flor"]].copy()

    output_path = Path(normalize_path(settings.PPROCESADO_OUTPUT_PATH))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_export.to_csv(output_path, index=False)

    dataframe_to_sql(df_export, "ld_producto_procesado", if_exists="replace")

    return str(output_path)