from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.settings import settings
from app.services.utils.dbf_reader import normalize_path
from app.services.etl.helpers import create_date_table, pico, safe_int_series, validate_columns


def _load_proyecciones_csv() -> pd.DataFrame:
    input_path = Path(normalize_path(settings.PROYECCIONES_OUTPUT_PATH))
    if not input_path.exists():
        from app.services.etl_jobs.proyecciones_generator import generate_proyecciones_csv

        generate_proyecciones_csv()

    if not input_path.exists():
        raise FileNotFoundError(
            "No existe proyecciones.csv y no se pudo regenerar automaticamente."
        )

    df = pd.read_csv(input_path, low_memory=False)
    df.columns = [str(column).strip().lower() for column in df.columns]

    required = {"finca", "flor", "bloque", "variedad", "cosecha", "fecha", "matas", "edad", "tipo", "tallos"}
    validate_columns(df, required, "proyecciones.csv")
    return df


def _normalize_tipo(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.strip()
        .replace({"Pto": "PT", "Real": "RE", "PT": "PT", "RE": "RE"})
    )


def _normalize_finca(series: pd.Series) -> pd.Series:
    # Conserva finca como texto y rellena con ceros para mantener codigos tipo 001.
    cleaned = series.astype(str).str.strip()
    as_num = pd.to_numeric(cleaned, errors="coerce")
    normalized = cleaned.where(as_num.isna(), as_num.round().astype("Int64").astype(str).str.zfill(3))
    return normalized


def _build_date_dim() -> pd.DataFrame:
    date_dim = create_date_table(
        settings.PRODUCCION_PICOS_DATE_START,
        settings.PRODUCCION_PICOS_DATE_END,
    )
    return date_dim[["fecha", "aass", "año", "semana"]]


def generate_produccion_picos_report() -> str:
    df = _load_proyecciones_csv()

    df = df.copy()
    df["tipo"] = _normalize_tipo(df["tipo"])
    df = df[df["tipo"].isin(["PT", "RE"])].copy()

    df = df.rename(columns={"variedad": "nvariedad", "matas": "plantas"})
    df.insert(3, "variedad", "0000")
    df["finca"] = _normalize_finca(df["finca"])

    df["flor"] = df["flor"].astype(str).str.strip()
    df = df[df["flor"].isin(settings.PRODUCCION_PICOS_FLOR_FILTER)].copy()

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.normalize()
    df = df[df["fecha"].notna()].copy()

    for numeric_col in ["bloque", "plantas", "edad", "tallos"]:
        df[numeric_col] = safe_int_series(df[numeric_col])

    df_dates = _build_date_dim()
    df = df.merge(df_dates, on="fecha", how="left")
    df = df[df["año"].notna() & df["semana"].notna()].copy()

    df_end = (
        df.groupby(
            ["finca", "bloque", "flor", "variedad", "nvariedad", "cosecha", "tipo", "año", "semana", "aass"],
            dropna=False,
        )
        .agg({"plantas": "mean", "tallos": "sum", "edad": "mean"})
        .reset_index()
    )

    df_end["bloque"] = safe_int_series(df_end["bloque"]).round().astype(int)
    df_end["plantas"] = safe_int_series(df_end["plantas"]).round().astype(int)
    df_end["tallos"] = safe_int_series(df_end["tallos"]).round().astype(int)
    df_end["edad"] = safe_int_series(df_end["edad"]).round().astype(int)
    df_end["año"] = safe_int_series(df_end["año"]).round().astype(int)
    df_end["semana"] = safe_int_series(df_end["semana"]).round().astype(int)
    df_end["aass"] = safe_int_series(df_end["aass"]).round().astype(int)
    df_end["pico"] = df_end["edad"].apply(pico)
    df_end["cosecha"] = df_end["cosecha"].astype(str).str.strip().replace({"OHS24": "OH24S"})

    output_path = Path(normalize_path(settings.PRODUCCION_PICOS_OUTPUT_PATH))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_end.to_csv(output_path, index=False)

    return str(output_path)