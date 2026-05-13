from __future__ import annotations

import pandas as pd

from app.core.settings import settings
from app.services.etl_helpers import dataframe_to_sql, read_dbf, validate_columns


def load_maestra_fusarium() -> str:
    df = read_dbf(settings.LOAD_FUSARIUM_PATH)
    if df.empty:
        raise RuntimeError("El archivo historico_fusarium.dbf no contiene datos.")

    validate_columns(
        df,
        {"finca", "flor", "bloque", "cosecha", "nvari", "fecha", "ncolor", "sustrato", "pico", "porc", "estadoact", "matas", "matfus"},
        "historico_fusarium.dbf",
    )

    df_export = df[["finca", "flor", "bloque", "cosecha", "nvari", "fecha", "ncolor", "sustrato", "pico", "porc", "estadoact", "matas", "matfus"]].copy()
    df_export["fecha"] = pd.to_datetime(df_export["fecha"], errors="coerce")
    df_export = df_export[df_export["fecha"].notna()].copy()
    df_export = df_export.sort_values(by=["finca", "flor", "nvari", "cosecha", "fecha"]) 

    group_cols = ["finca", "flor", "nvari", "cosecha"]
    max_fecha = df_export.groupby(group_cols)["fecha"].transform("max")
    df_export["ultimo"] = df_export["fecha"] == max_fecha

    dataframe_to_sql(df_export, "ld_fusarium", if_exists="replace")
    return "mysql:informes.ld_fusarium"