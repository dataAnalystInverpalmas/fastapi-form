from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.settings import settings
from app.services.etl.helpers import dataframe_to_sql, validate_columns
from app.services.utils.dbf_reader import normalize_path

RAW_COLUMN_MAP = {
    "Flor": "flor",
    "Color": "color",
    "Item Demanda": "item_demanda",
    "Tipo": "tipo",
    "Mercado": "mercado",
    "Submercado": "submercado",
    "Semana": "semana",
    "Semana enraizamiento": "semana_enraizamiento",
    "Fecha": "fecha",
    "Cantidad": "cantidad",
    "Cantidad para enraizar": "cantidad_enraizar",
    "Precio": "precio",
    "Grupo de demanda": "grupo_demanda",
}

TEXT_COLUMNS = [
    "flor",
    "color",
    "item_demanda",
    "tipo",
    "mercado",
    "submercado",
    "grupo_demanda",
]

WEEK_CODE_COLUMNS = [
    "semana",
    "semana_enraizamiento",
]

# Tika exporta 'Cantidad'/'Cantidad para enraizar' con el punto como separador
# de miles (p.ej. "11.000" == 11000 tallos), no como separador decimal.
THOUSANDS_COLUMNS = [
    "cantidad",
    "cantidad_enraizar",
]

# Columnas que deben leerse como texto para no perder el formato original
# (dtype numérico automático de pandas destruye el punto de miles / ceros a la izquierda).
STRING_READ_COLUMNS = [
    "Semana",
    "Semana enraizamiento",
    "Cantidad",
    "Cantidad para enraizar",
]


def prepare_tika_demanda_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    validate_columns(df, set(RAW_COLUMN_MAP.keys()), "demanda_27-28v4.csv")

    df_export = df[list(RAW_COLUMN_MAP.keys())].rename(columns=RAW_COLUMN_MAP).copy()
    df_export = df_export[df_export["flor"].notna()].reset_index(drop=True)

    for column in TEXT_COLUMNS + WEEK_CODE_COLUMNS:
        df_export[column] = df_export[column].astype(str).str.strip()

    df_export["fecha"] = pd.to_datetime(df_export["fecha"], errors="coerce")

    for column in THOUSANDS_COLUMNS:
        cleaned = df_export[column].astype(str).str.strip().str.replace(".", "", regex=False)
        df_export[column] = pd.to_numeric(cleaned, errors="coerce")

    df_export["precio"] = pd.to_numeric(df_export["precio"], errors="coerce")

    return df_export


def load_tika_demanda() -> str:
    csv_path = Path(normalize_path(settings.TIKA_DEMANDA_PATH))
    if not csv_path.exists():
        raise FileNotFoundError(f"No existe el archivo de demanda Tika: {csv_path}")

    df = pd.read_csv(
        csv_path,
        encoding="utf-8-sig",
        dtype={column: str for column in STRING_READ_COLUMNS},
    )
    if df.empty:
        raise RuntimeError("El archivo de demanda Tika no contiene datos.")

    df_export = prepare_tika_demanda_dataframe(df)

    dataframe_to_sql(df_export, "tika_demanda", if_exists="replace")
    return "mysql:informes.tika_demanda"
