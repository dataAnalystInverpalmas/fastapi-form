from __future__ import annotations

from app.core.settings import settings
from app.services.etl.helpers import dataframe_to_sql, read_dbf, validate_columns


def load_maestra_cosechas() -> str:
    df = read_dbf(settings.LOAD_MCOSE_PATH)
    if df.empty:
        raise RuntimeError("El archivo ld_mcose.dbf no contiene datos.")

    validate_columns(df, {"codigo", "nombre", "fiesta"}, "ld_mcose.dbf")

    df_export = df[["codigo", "nombre", "fiesta"]].copy()

    dataframe_to_sql(df_export, "ld_cosechas", if_exists="replace")
    return "mysql:informes.ld_cosechas"