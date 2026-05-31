from __future__ import annotations

import pandas as pd

from app.core.settings import settings
from app.services.etl.helpers import dataframe_to_sql, read_dbf, read_many_dbf, validate_columns


def load_maestra_lonas() -> str:
    df_lonas = read_many_dbf(settings.LOAD_LD_BCULT_DIR, settings.LOAD_LONAS_FILES)
    if df_lonas.empty:
        raise RuntimeError("No se encontraron datos en lonasYYYY.dbf.")

    validate_columns(
        df_lonas,
        {"fecha", "fsiemb", "finca", "bloque", "cosecha", "flor", "variedad", "lonas", "tmatab"},
        "lonasYYYY.dbf",
    )
    df_lonas["fecha"] = pd.to_datetime(df_lonas["fecha"], errors="coerce")
    df_lonas["fsiemb"] = pd.to_datetime(df_lonas["fsiemb"], errors="coerce")
    df_lonas = df_lonas[df_lonas["fecha"].notna()].copy()

    df_vari = read_dbf(settings.LOAD_MVARI_PATH)
    if df_vari.empty:
        raise RuntimeError("El archivo ld_mvari.dbf no contiene datos para el catalogo de variedades.")

    validate_columns(df_vari, {"codigo", "nombre", "codflor"}, "ld_mvari.dbf")
    df_vari = df_vari.rename(columns={"codigo": "variedad", "nombre": "nvari", "codflor": "flor_vari"})

    df_lonas = df_lonas.rename(columns={"flor": "flor_lonas"})
    df = pd.merge(df_lonas, df_vari[["variedad", "nvari", "flor_vari"]], on="variedad", how="left")
    df["flor"] = df["flor_lonas"].fillna(df["flor_vari"])

    df_export = df[["fecha", "fsiemb", "finca", "bloque", "cosecha", "flor", "nvari", "lonas", "tmatab"]].copy()
    df_export = df_export.rename(
        columns={
            "fsiemb": "fecha_siembra",
            "nvari": "variedad",
            "lonas": "tallos",
            "tmatab": "plantas",
        }
    )
    df_export["fecha"] = pd.to_datetime(df_export["fecha"], errors="coerce")
    df_export["fecha_siembra"] = pd.to_datetime(df_export["fecha_siembra"], errors="coerce")
    df_export = df_export[df_export["fecha"].notna()].copy()

    dataframe_to_sql(df_export, "ld_lonas", if_exists="replace")
    return "mysql:informes.ld_lonas"