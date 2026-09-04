from __future__ import annotations

from app.core.settings import settings
from app.services.etl.helpers import dataframe_to_sql, read_dbf, validate_columns


def load_maestra_variedades() -> str:
    df = read_dbf(settings.LOAD_MVARI_PATH)
    if df.empty:
        raise RuntimeError("El archivo ld_mvari.dbf no contiene datos.")

    validate_columns(df, {"codigo", "nombre", "codflor", "codgcol", "activo"}, "ld_mvari.dbf")

    df_export = df[["codigo", "nombre", "codflor", "codgcol", "activo"]].copy()
    df_export = df_export[df_export["activo"] == True].copy()  # noqa: E712
    df_export = df_export[df_export["codflor"].isin(settings.LOAD_VARIEDADES_FLOR_FILTER)].copy()
    df_export["nombre"] = df_export["nombre"].astype(str).str.strip()
    df_export = df_export[~df_export["nombre"].str.endswith("_")].copy()

    dataframe_to_sql(df_export, "ld_variedades", if_exists="replace")
    return "mysql:informes.ld_variedades"