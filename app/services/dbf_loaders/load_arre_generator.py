from __future__ import annotations

import pandas as pd

from app.core.settings import settings
from app.services.etl.helpers import dataframe_to_sql, read_dbf, read_many_dbf, validate_columns


REQUIRED_COLUMNS = {"tipo", "fecha", "finca", "flor", "variedad", "bloque", "tallos", "cosecha"}


def prepare_arre_dataframe(df: pd.DataFrame, variedades_catalog: pd.DataFrame | None = None) -> pd.DataFrame:
    """Filtra, normaliza y enriquece los datos ARRE para la carga consolidada."""
    validate_columns(df, REQUIRED_COLUMNS, "arre*.dbf")

    df_export = df[["tipo", "fecha", "finca", "flor", "variedad", "bloque", "tallos", "cosecha"]].copy()
    df_export["tipo"] = df_export["tipo"].astype(str).str.strip().str.upper()
    df_export["fecha"] = pd.to_datetime(df_export["fecha"], errors="coerce")
    df_export = df_export[(df_export["tipo"] != "MA") & df_export["fecha"].notna()].copy()
    df_export = df_export[
        (df_export["fecha"].dt.year >= settings.LOAD_ARRE_ANIO_INICIO)
        & (df_export["fecha"].dt.year <= settings.LOAD_ARRE_ANIO_FIN)
    ].copy()

    df_export["finca"] = df_export["finca"].astype(str).str.strip()
    df_export["flor"] = df_export["flor"].astype(str).str.strip().str.upper()
    df_export["variedad"] = df_export["variedad"].astype(str).str.strip().str.upper()
    df_export["bloque"] = pd.to_numeric(df_export["bloque"], errors="coerce")

    cosecha_series = df_export["cosecha"].astype("string")
    cosecha_series = cosecha_series.str.strip()
    cosecha_series = cosecha_series.replace({pd.NA: None, "": None})
    df_export["cosecha"] = cosecha_series.where(cosecha_series.notna(), None)
    df_export["cosecha"] = df_export["cosecha"].astype("string")

    if variedades_catalog is None:
        variedades_catalog = read_dbf(settings.LOAD_MVARI_PATH)
        if variedades_catalog.empty:
            raise RuntimeError("El archivo ld_mvari.dbf no contiene datos para enriquecer ARRE.")
    if {"codigo", "nombre"}.issubset(variedades_catalog.columns):
        variedades_catalog = variedades_catalog[["codigo", "nombre"]].copy()
        variedades_catalog = variedades_catalog.rename(columns={"codigo": "variedad", "nombre": "nombre_variedad"})
    elif {"variedad", "nombre_variedad"}.issubset(variedades_catalog.columns):
        variedades_catalog = variedades_catalog[["variedad", "nombre_variedad"]].copy()
    else:
        validate_columns(variedades_catalog, {"codigo", "nombre"}, "variedades_catalog")
        variedades_catalog = variedades_catalog[["codigo", "nombre"]].copy()
        variedades_catalog = variedades_catalog.rename(columns={"codigo": "variedad", "nombre": "nombre_variedad"})

    variedades_catalog["variedad"] = variedades_catalog["variedad"].astype(str).str.strip().str.upper()
    variedades_catalog["nombre_variedad"] = variedades_catalog["nombre_variedad"].astype(str).str.strip()

    df_export = pd.merge(
        df_export,
        variedades_catalog[["variedad", "nombre_variedad"]].drop_duplicates(subset=["variedad"], keep="first"),
        on="variedad",
        how="left",
    )
    df_export["nombre_variedad"] = df_export["nombre_variedad"].fillna(df_export["variedad"])

    return df_export


def load_maestra_arre() -> str:
    """Carga los archivos ARRE del directorio ld_bcult para el rango de años configurado."""
    filenames = [
        f"arre{year}.dbf"
        for year in range(settings.LOAD_ARRE_ANIO_INICIO, settings.LOAD_ARRE_ANIO_FIN + 1)
    ]
    df = read_many_dbf(settings.LOAD_LD_BCULT_DIR, filenames)
    if df.empty:
        raise RuntimeError("No se encontraron datos en los archivos arreYYYY.dbf.")

    df_export = prepare_arre_dataframe(df)
    if df_export.empty:
        raise RuntimeError(
            f"No quedaron registros válidos después de filtrar tipo MA y rango "
            f"{settings.LOAD_ARRE_ANIO_INICIO}-{settings.LOAD_ARRE_ANIO_FIN}."
        )

    dataframe_to_sql(df_export, "ld_arre", if_exists="replace")
    return "mysql:informes.ld_arre"
