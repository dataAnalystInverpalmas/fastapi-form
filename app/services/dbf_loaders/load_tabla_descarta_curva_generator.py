from __future__ import annotations

import pandas as pd

from app.core.settings import settings
from app.services.etl.helpers import dataframe_to_sql, read_dbf, validate_columns


def _build_variedades_catalog() -> pd.DataFrame:
    df_vari = read_dbf(settings.LOAD_MVARI_PATH)
    if df_vari.empty:
        raise RuntimeError("El archivo ld_mvari.dbf no contiene datos para el catalogo de variedades.")

    validate_columns(df_vari, {"codigo", "nombre", "codflor"}, "ld_mvari.dbf")

    df_vari = df_vari[df_vari["codflor"].isin(settings.LOAD_METAS_FLOR_FILTER)].copy()
    df_vari = df_vari[["codigo", "nombre"]].copy()
    df_vari = df_vari.rename(columns={"codigo": "variedad", "nombre": "nvariedad"})
    return df_vari


def load_tabla_descarta_curva() -> str:
    df_vari = _build_variedades_catalog()

    df = read_dbf(settings.LOAD_DESCARTA_CURVA_PATH)
    if df.empty:
        raise RuntimeError("El archivo descarta_curva.dbf no contiene datos.")

    validate_columns(df, {"finca", "bloque", "variedad", "cosecha"}, "descarta_curva.dbf")

    df_export = df[["finca", "bloque", "variedad", "cosecha"]].copy()
    df_export = pd.merge(df_export, df_vari, how="left", on="variedad")

    dataframe_to_sql(df_export, "ld_descarta_curva", if_exists="replace")
    return "mysql:informes.ld_descarta_curva"