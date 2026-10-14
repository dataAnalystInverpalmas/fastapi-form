from __future__ import annotations

import re
from typing import Iterable

import pandas as pd
from sqlalchemy import inspect, text

from app.core.settings import settings
from app.services.etl.helpers import _get_engine, read_dbf, read_many_dbf, validate_columns
from app.services.utils.date_service import get_bogota_now

TABLE_NAME = "ld_lonas"
_YEAR_IN_FILENAME = re.compile(r"(\d{4})")


def _file_year(filename: str) -> int | None:
    match = _YEAR_IN_FILENAME.search(filename)
    return int(match.group(1)) if match else None


def select_recent_files(filenames: Iterable[str], anio_corte: int) -> list[str]:
    """Filtra lonasYYYY.dbf cuyo año sea >= anio_corte (cada archivo solo trae fechas de su año)."""
    return [name for name in filenames if (_file_year(name) or 0) >= anio_corte]


def prepare_lonas_dataframe(df_lonas: pd.DataFrame, df_vari: pd.DataFrame) -> pd.DataFrame:
    validate_columns(
        df_lonas,
        {"fecha", "fsiemb", "finca", "bloque", "cosecha", "flor", "variedad", "lonas", "tmatab"},
        "lonasYYYY.dbf",
    )
    # Conservar solo las columnas necesarias para evitar sobrecarga en merge y carga SQL.
    df_lonas = df_lonas[["fecha", "fsiemb", "finca", "bloque", "cosecha", "flor", "variedad", "lonas", "tmatab"]].copy()
    df_lonas["fecha"] = pd.to_datetime(df_lonas["fecha"], errors="coerce")
    df_lonas["fsiemb"] = pd.to_datetime(df_lonas["fsiemb"], errors="coerce")
    df_lonas = df_lonas[df_lonas["fecha"].notna()].copy()

    validate_columns(df_vari, {"codigo", "nombre", "codflor"}, "ld_mvari.dbf")
    df_vari = df_vari.rename(columns={"codigo": "variedad", "nombre": "nvari", "codflor": "flor_vari"})

    df_lonas = df_lonas.rename(columns={"flor": "flor_lonas"})
    df = pd.merge(df_lonas, df_vari[["variedad", "nvari", "flor_vari"]], on="variedad", how="left")
    df["flor"] = df["flor_lonas"].fillna(df["flor_vari"])

    df_export = df[["fecha", "fsiemb", "finca", "bloque", "cosecha", "flor", "nvari", "lonas", "tmatab"]].copy()
    return df_export.rename(
        columns={
            "fsiemb": "fecha_siembra",
            "nvari": "variedad",
            "lonas": "tallos",
            "tmatab": "plantas",
        }
    )


def load_maestra_lonas() -> str:
    engine = _get_engine()
    anios_recarga = int(settings.LOAD_LONAS_ANIOS_RECARGA)
    incremental = anios_recarga > 0 and inspect(engine).has_table(TABLE_NAME)

    filenames = list(settings.LOAD_LONAS_FILES)
    fecha_corte: pd.Timestamp | None = None
    if incremental:
        anio_corte = get_bogota_now().year - anios_recarga + 1
        fecha_corte = pd.Timestamp(year=anio_corte, month=1, day=1)
        filenames = select_recent_files(filenames, anio_corte)
        if not filenames:
            raise RuntimeError(
                f"LOAD_LONAS_FILES no incluye archivos lonasYYYY.dbf desde {anio_corte}."
            )

    df_lonas = read_many_dbf(settings.LOAD_LD_BCULT_DIR, filenames)
    if df_lonas.empty:
        raise RuntimeError("No se encontraron datos en lonasYYYY.dbf.")

    df_vari = read_dbf(settings.LOAD_MVARI_PATH)
    if df_vari.empty:
        raise RuntimeError("El archivo ld_mvari.dbf no contiene datos para el catalogo de variedades.")

    df_export = prepare_lonas_dataframe(df_lonas, df_vari)

    if fecha_corte is None:
        df_export.to_sql(TABLE_NAME, engine, index=False, if_exists="replace")
        return f"mysql:informes.{TABLE_NAME} (recarga completa: {len(df_export)} filas)"

    # Lo que quede antes del corte ya está en la tabla; no reinsertarlo evita duplicados.
    df_export = df_export[df_export["fecha"] >= fecha_corte]
    # Borrado + inserción en una sola transacción: si la carga falla, la tabla queda como estaba.
    with engine.begin() as connection:
        connection.execute(
            text(f"DELETE FROM `{TABLE_NAME}` WHERE fecha >= :corte"),
            {"corte": fecha_corte.to_pydatetime()},
        )
        df_export.to_sql(TABLE_NAME, connection, index=False, if_exists="append")
    return (
        f"mysql:informes.{TABLE_NAME} (incremental desde {fecha_corte.date()}: "
        f"{len(df_export)} filas recargadas)"
    )
