from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from app.core.settings import settings
from app.services.utils.dbf_reader import normalize_path


REQUIRED_COLUMNS: set[str] = {
    "bodega",
    "finca",
    "codigo",
    "fecha",
    "semana",
    "producto",
    "color",
    "variedad",
    "grado",
    "apertura",
    "dias",
    "tallos",
    "tallos_por_ramo",
    "ramos",
    "unidades",
    "unidad",
}


def _read_table(input_path: str) -> pd.DataFrame:
    path = Path(normalize_path(input_path))
    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo de entrada: {path}")

    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    elif suffix == ".csv":
        df = pd.read_csv(path, low_memory=False)
    elif suffix == ".dbf":
        from app.services.etl.helpers import read_dbf

        df = read_dbf(str(path))
    else:
        raise ValueError(f"Formato no soportado para '{path.name}': {suffix or 'sin extension'}")

    df = df.copy()
    df.columns = [str(col).strip().lower() for col in df.columns]
    return df


def _transform_data(df: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Columnas faltantes: {', '.join(sorted(missing))}")

    result = df.copy()
    result["fecha"] = pd.to_datetime(result["fecha"], errors="coerce", dayfirst=True)
    if result["fecha"].isna().any():
        raise ValueError("Hay fechas invalidas en la columna 'fecha'.")

    iso_week = result["fecha"].dt.isocalendar().week.astype(str).str.zfill(2)
    result["semana"] = result["fecha"].dt.strftime("%y") + iso_week
    result["variedad"] = (
        result["variedad"].astype(str).str.strip().str.replace(r"\s+", "_", regex=True)
    )
    return result


def generate_process_guarde(params: dict[str, Any] | None = None) -> str:
    params = params or {}
    input_path = str(params.get("input_path") or settings.PROCESS_GUARDE_INPUT_PATH).strip()
    output_path = str(params.get("output_path") or settings.PROCESS_GUARDE_OUTPUT_PATH).strip()

    if not input_path:
        raise RuntimeError("Configura 'input_path' para ejecutar el job load_process_guarde.")

    df_raw = _read_table(input_path)
    if df_raw.empty:
        raise RuntimeError("El archivo de entrada no contiene datos.")

    df_out = _transform_data(df_raw)

    output_file = Path(normalize_path(output_path))
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_excel(output_file, index=False)
    return str(output_file)