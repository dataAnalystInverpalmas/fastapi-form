from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from app.core.settings import settings
from app.services.utils.dbf_reader import normalize_path
from app.services.etl.helpers import (
    dataframe_to_sql,
    execute_query,
    read_dbf,
    safe_int_series,
    validate_columns,
)


REQUIRED_COLUMNS = {"flor", "tallos", "ano", "fuente", "grado", "fecha", "finca", "bloque", "variedad"}
EXPORT_COLUMNS = ["finca", "bloque", "nvari", "grado", "tallos", "fecha", "fuente", "flor"]
SQL_SNAPSHOT_QUERY = (
    "SELECT finca, bloque, nvari, grado, tallos, fecha, fuente, flor "
    "FROM ld_producto_procesado"
)


def _build_variedades_catalog() -> pd.DataFrame:
    rows = execute_query("SELECT codigo, nombre FROM ld_variedades") or []
    df_vari = pd.DataFrame(rows, columns=["variedad", "nvari"])
    if df_vari.empty:
        raise RuntimeError("No se encontraron datos en ld_variedades para enriquecer nvari.")

    df_vari["variedad"] = df_vari["variedad"].astype(str).str.strip()
    df_vari["nvari"] = df_vari["nvari"].astype(str).str.strip()
    return df_vari.drop_duplicates(subset=["variedad"], keep="first")


def _asignar_grado(df: pd.DataFrame) -> pd.DataFrame:

    df = df.copy()

    df["grado"] = np.where(
        df["grado"].isin(["SEL", "080", "070", "090", "100"]),
        "SEL",
        np.where(
            df["grado"].isin(["FAN", "060"]),
            "FAN",
            np.where(
                df["grado"].isin(["STD", "050"]),
                "STD",
                np.where(
                    df["grado"].isin(["SHR", "040", "030"]),
                    "SHR",
                    df["grado"],
                ),
            ),
        ),
    )

    return df


def _read_optional(path: str, source_name: str, missing_sources: list[str]) -> pd.DataFrame:
    try:
        return read_dbf(path)
    except FileNotFoundError:
        missing_sources.append(f"{source_name}: {normalize_path(path)}")
        return pd.DataFrame()


def _validate_required_columns(df: pd.DataFrame, source_name: str) -> None:
    if not df.empty:
        validate_columns(df, REQUIRED_COLUMNS, source_name)


def _filter_historico_year(df: pd.DataFrame, year: int) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=list(REQUIRED_COLUMNS))

    filtro_flor = settings.PPROCESADO_FLOR_FILTER
    filtro_fuente = settings.PPROCESADO_FUENTE_FILTER
    ano = pd.to_numeric(df["ano"], errors="coerce")
    tallos = safe_int_series(df["tallos"])

    return df[
        (df["flor"].isin(filtro_flor))
        & (tallos != 0)
        & (ano == year)
        & (df["fuente"].isin(filtro_fuente))
    ].copy()


def _filter_incremental(df: pd.DataFrame, fecha_inicio: pd.Timestamp) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=list(REQUIRED_COLUMNS))

    filtro_flor = settings.PPROCESADO_FLOR_FILTER
    filtro_fuente = settings.PPROCESADO_FUENTE_FILTER
    fechas = pd.to_datetime(df["fecha"], errors="coerce").dt.normalize()
    tallos = safe_int_series(df["tallos"])

    filtered = df[
        (df["flor"].isin(filtro_flor))
        & (tallos != 0)
        & (df["fuente"].isin(filtro_fuente))
        & (fechas >= fecha_inicio)
    ].copy()
    return filtered


def _build_export_from_rows(df_rows: pd.DataFrame) -> pd.DataFrame:
    if df_rows.empty:
        return pd.DataFrame(columns=EXPORT_COLUMNS)

    df_rows = _asignar_grado(df_rows)
    df_rows = df_rows[["finca", "bloque", "variedad", "grado", "tallos", "fecha", "fuente", "flor"]].copy()
    df_rows["tallos"] = safe_int_series(df_rows["tallos"]).astype(int)
    df_rows["fecha"] = pd.to_datetime(df_rows["fecha"], errors="coerce").dt.normalize()
    df_rows = df_rows.dropna(subset=["fecha"]).copy()
    df_rows["variedad"] = df_rows["variedad"].astype(str).str.strip()

    df_vari = _build_variedades_catalog()
    df_export = pd.merge(df_rows, df_vari, how="left", on="variedad")
    df_export["nvari"] = df_export["nvari"].fillna(df_export["variedad"])
    return df_export[EXPORT_COLUMNS].copy()


def _build_historico_export() -> pd.DataFrame:
    missing_sources: list[str] = []
    historicos = [
        (2021, settings.PPROCESADO_2021_PATH, "pprocesado_2021"),
        (2022, settings.PPROCESADO_2022_PATH, "pprocesado_2022"),
        (2023, settings.PPROCESADO_2023_PATH, "pprocesado_2023"),
        (2024, settings.PPROCESADO_2024_PATH, "pprocesado_2024"),
        (2025, settings.PPROCESADO_2025_PATH, "pprocesado_2025"),
    ]

    filtered_parts: list[pd.DataFrame] = []
    for year, path, source_name in historicos:
        df_source = _read_optional(path=path, source_name=source_name, missing_sources=missing_sources)
        _validate_required_columns(df_source, source_name)
        filtered_parts.append(_filter_historico_year(df_source, year=year))

    df_final = pd.concat(filtered_parts, ignore_index=True)
    if df_final.empty:
        missing_msg = ""
        if missing_sources:
            missing_msg = " Archivos faltantes: " + "; ".join(missing_sources)
        raise RuntimeError("No hay datos historicos de producto procesado para exportar." + missing_msg)

    return _build_export_from_rows(df_final)


def _build_incremental_export(fecha_inicio: pd.Timestamp) -> pd.DataFrame:
    pprocesado = read_dbf(settings.PPROCESADO_CURRENT_PATH)
    _validate_required_columns(pprocesado, "pprocesado")

    df_final = _filter_incremental(pprocesado, fecha_inicio=fecha_inicio)
    if df_final.empty:
        raise RuntimeError(
            "No hay datos incrementales de producto procesado para exportar "
            f"desde {fecha_inicio.strftime('%Y-%m-%d')}."
        )

    return _build_export_from_rows(df_final)


def _delete_incremental_slice(fecha_inicio: pd.Timestamp) -> None:
    fecha_sql = fecha_inicio.strftime("%Y-%m-%d")
    execute_query(f"DELETE FROM ld_producto_procesado WHERE fecha >= '{fecha_sql}'")


def _export_snapshot_from_sql(fecha_inicio: pd.Timestamp | None = None) -> str:
    sql = SQL_SNAPSHOT_QUERY
    if fecha_inicio is not None:
        fecha_sql = fecha_inicio.strftime("%Y-%m-%d")
        sql += f" WHERE fecha >= '{fecha_sql}'"
    sql += " ORDER BY fecha, finca, bloque, nvari, grado, fuente, flor"

    rows = execute_query(sql) or []
    if not rows:
        raise RuntimeError("La tabla ld_producto_procesado no contiene datos para exportar.")

    df_export = pd.DataFrame(rows, columns=EXPORT_COLUMNS)
    df_export["tallos"] = safe_int_series(df_export["tallos"]).astype(int)
    df_export["fecha"] = pd.to_datetime(df_export["fecha"], errors="coerce").dt.normalize()
    df_export = df_export.dropna(subset=["fecha"]).copy()

    output_path = Path(normalize_path(settings.PPROCESADO_OUTPUT_PATH))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_export.to_csv(output_path, index=False)
    return str(output_path)


def generate_producto_procesado_historico_csv() -> str:
    df_export = _build_historico_export()
    dataframe_to_sql(df_export, "ld_producto_procesado", if_exists="replace")
    return "mysql:informes.ld_producto_procesado"


def generate_producto_procesado_csv(params: dict | None = None) -> str:
    raw_fecha_inicio = (params or {}).get(
        "fecha_inicio_incremental",
        settings.PPROCESADO_INCREMENTAL_START_DATE,
    )

    try:
        fecha_inicio = pd.to_datetime(raw_fecha_inicio, errors="raise").normalize()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("fecha_inicio_incremental debe tener formato valido (YYYY-MM-DD).") from exc

    raw_fecha_exportacion = (params or {}).get(
        "fecha_inicio_exportacion",
        settings.PPROCESADO_INCREMENTAL_START_DATE,
    )

    try:
        fecha_inicio_exportacion = pd.to_datetime(raw_fecha_exportacion, errors="raise").normalize()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("fecha_inicio_exportacion debe tener formato valido (YYYY-MM-DD).") from exc

    df_export = _build_incremental_export(fecha_inicio=fecha_inicio)
    _delete_incremental_slice(fecha_inicio=fecha_inicio)
    dataframe_to_sql(df_export, "ld_producto_procesado", if_exists="append")
    output_path = _export_snapshot_from_sql(fecha_inicio=fecha_inicio_exportacion)
    return str(output_path)