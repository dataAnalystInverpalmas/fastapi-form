from __future__ import annotations

from app.core.settings import settings
from app.services.etl_helpers import dataframe_to_sql, read_dbf, validate_columns


def load_maestra_fiestas() -> str:
    df = read_dbf(settings.LOAD_MFIES_PATH)
    if df.empty:
        raise RuntimeError("El archivo ld_mfies.dbf no contiene datos.")

    validate_columns(df, {"codigo", "nombre", "mes", "observa"}, "ld_mfies.dbf")

    df_export = df[["codigo", "nombre", "mes", "observa"]].copy()
    df_export["observa"] = df_export["observa"].astype(str).str.strip()
    df_export = df_export[df_export["observa"] != ""].copy()
    df_export = df_export.sort_values("mes")

    dataframe_to_sql(df_export, "ld_fiestas", if_exists="replace")
    return "mysql:informes.ld_fiestas"