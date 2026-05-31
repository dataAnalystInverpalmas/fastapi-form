from __future__ import annotations

import pandas as pd

from app.core.settings import settings
from app.services.etl.helpers import dataframe_to_sql, read_dbf, validate_columns


def _is_active_series(series: pd.Series) -> pd.Series:
    normalized = series.copy()

    if pd.api.types.is_bool_dtype(normalized):
        return ~normalized.fillna(False)

    normalized = normalized.astype(str).str.strip().str.lower()
    inactive_values = {"true", "1", "t", "y", "yes", "si", "s", "x"}
    return ~normalized.isin(inactive_values)


def load_maestra_causas() -> str:
    df = read_dbf(settings.LOAD_MCAUS_PATH)
    if df.empty:
        raise RuntimeError("El archivo ld_mcaus.dbf no contiene datos.")

    validate_columns(df, {"inactivo"}, "ld_mcaus.dbf")

    df_export = df.copy()
    df_export = df_export[_is_active_series(df_export["inactivo"])].copy()

    if "codigo" in df_export.columns:
        df_export["codigo"] = df_export["codigo"].astype(str).str.strip()
    if "nombre" in df_export.columns:
        df_export["nombre"] = df_export["nombre"].astype(str).str.strip()
    if "fito" in df_export.columns:
        df_export["fito"] = pd.to_numeric(df_export["fito"], errors="coerce").fillna(0).astype(int)

    dataframe_to_sql(df_export, "ld_causas", if_exists="replace")
    return "mysql:informes.ld_causas"