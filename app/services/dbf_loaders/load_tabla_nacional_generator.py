from __future__ import annotations

import pandas as pd
from typing import Any

from app.core.settings import settings
from app.services.etl.helpers import (
    dataframe_to_sql,
    execute_query,
    normalize_finca_series,
    read_dbf,
    read_many_dbf,
    validate_columns,
)


def _resolve_rflo_filenames(params: dict[str, Any] | None = None) -> list[str]:
    raw_tables = (params or {}).get("rflo_tables", settings.LOAD_RFLO_NACIONAL_TABLES)
    tables = raw_tables if isinstance(raw_tables, list) else [raw_tables]

    filenames: list[str] = []
    for table in tables:
        token = str(table).strip()
        if not token:
            continue
        if not token.lower().endswith(".dbf"):
            token = f"{token}.dbf"
        filenames.append(token)

    if filenames:
        return filenames

    # La ruta puede venir como \\servidor\... o //servidor/...
    fallback_name = settings.LOAD_RFLO_NACIONAL_PATH.replace("\\", "/").split("/")[-1].strip()
    if fallback_name:
        return [fallback_name]
    raise RuntimeError("No se definieron tablas rflo para cargar ld_nacional.")


def _build_variedades_catalog() -> pd.DataFrame:
    rows = execute_query("SELECT codigo, nombre FROM ld_variedades") or []
    df_vari = pd.DataFrame(rows, columns=["variedad", "nvari"])
    if df_vari.empty:
        raise RuntimeError("No se encontraron datos en ld_variedades para enriquecer rflo2026.dbf.")

    df_vari["variedad"] = df_vari["variedad"].astype(str).str.strip()
    df_vari["nvari"] = df_vari["nvari"].astype(str).str.strip()
    return df_vari.drop_duplicates(subset=["variedad"], keep="first")


def _build_causas_catalog() -> pd.DataFrame:
    rows = execute_query("SELECT codigo, nombre, fito FROM ld_causas") or []
    df_causas = pd.DataFrame(rows, columns=["enfe", "problema", "fito"])
    if df_causas.empty:
        raise RuntimeError("No se encontraron datos en ld_causas para enriquecer rflo2026.dbf.")

    df_causas["enfe"] = df_causas["enfe"].astype(str).str.strip()
    df_causas["problema"] = df_causas["problema"].astype(str).str.strip()
    df_causas["fito_priority"] = df_causas["fito"].fillna(0).astype(int).eq(1).map({True: 0, False: 1})
    df_causas = df_causas.sort_values(by=["enfe", "fito_priority", "problema"])
    return df_causas.drop_duplicates(subset=["enfe"], keep="first")[["enfe", "problema"]]


def load_tabla_nacional(params: dict[str, Any] | None = None) -> str:
    filenames = _resolve_rflo_filenames(params)
    df = read_many_dbf(settings.LOAD_LD_BCULT_DIR, filenames)
    if df.empty and len(filenames) == 1:
        df = read_dbf(settings.LOAD_RFLO_NACIONAL_PATH)
    if df.empty:
        raise RuntimeError("Los archivos rflo seleccionados no contienen datos.")

    validate_columns(
        df,
        {"fecha", "finca", "bloque", "flor", "variedad", "enfe", "tallos", "grado", "muestra", "fuente"},
        ", ".join(filenames),
    )

    df_vari = _build_variedades_catalog()
    df_causas = _build_causas_catalog()

    df_export = df[["fecha", "finca", "bloque", "flor", "variedad", "enfe", "tallos", "grado", "muestra", "fuente"]].copy()
    df_export["fecha"] = pd.to_datetime(df_export["fecha"], errors="coerce").dt.normalize()
    df_export = df_export[df_export["fecha"].notna()].copy()

    for col in ["flor", "variedad", "enfe", "grado", "fuente"]:
        df_export[col] = df_export[col].astype(str).str.strip()

    df_export["finca"] = normalize_finca_series(df_export["finca"])
    df_export["bloque"] = pd.to_numeric(df_export["bloque"], errors="coerce").astype("Int64")
    df_export["tallos"] = pd.to_numeric(df_export["tallos"], errors="coerce").astype("Int64")
    df_export["muestra"] = pd.to_numeric(df_export["muestra"], errors="coerce").astype("Int64")

    df_export = pd.merge(df_export, df_vari, how="left", on="variedad")
    df_export = pd.merge(df_export, df_causas, how="left", on="enfe")

    df_export["nvari"] = df_export["nvari"].fillna(df_export["variedad"])
    df_export["problema"] = df_export["problema"].fillna(df_export["enfe"])

    df_export = df_export[["nvari", "bloque", "flor", "finca", "grado", "fuente", "problema", "tallos", "fecha", "muestra"]].copy()
    df_export = df_export.rename(columns={"nvari": "variedad"})

    dataframe_to_sql(df_export, "ld_nacional", if_exists="replace")
    return "mysql:informes.ld_nacional"