from __future__ import annotations

from app.core.settings import settings
from app.services.etl.helpers import dataframe_to_sql, read_dbf, validate_columns


def load_maestra_colores() -> str:
    df = read_dbf(settings.LOAD_MGCOL_PATH)
    if df.empty:
        raise RuntimeError("El archivo ld_mgcol.dbf no contiene datos.")

    validate_columns(df, {"codigo", "nombre", "observa"}, "ld_mgcol.dbf")

    df_export = df[["codigo", "nombre", "observa"]].copy()
    df_export = df_export.rename(columns={"observa": "orden"})

    dataframe_to_sql(df_export, "ld_colores", if_exists="replace")
    return "mysql:informes.ld_colores"