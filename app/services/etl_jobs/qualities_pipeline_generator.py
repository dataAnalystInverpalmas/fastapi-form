from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.settings import settings
from app.services.utils.dbf_reader import normalize_path
from app.services.etl.helpers import (
    resolve_date_range_params,
    validate_columns,
)


ALL_FARMS_CODE = settings.ALL_FARMS_CODE  # codigo de "todas las fincas consolidadas"


def _build_qualities_export_rows(df_cal: pd.DataFrame) -> pd.DataFrame:
    df_export = (
        df_cal.groupby(["finca", "nvari", "grado"], as_index=False)["tallos"]
        .sum()
    )
    df_export["aporte"] = (
        df_export.groupby(["finca", "nvari"])["tallos"]
        .transform(lambda values: values / values.sum())
    )
    df_all_farms = (
        df_cal.groupby(["nvari", "grado"], as_index=False)["tallos"]
        .sum()
    )
    df_all_farms["aporte"] = (
        df_all_farms.groupby(["nvari"])["tallos"]
        .transform(lambda values: values / values.sum())
    )
    df_all_farms["finca"] = ALL_FARMS_CODE
    df_all_farms = df_all_farms[["finca", "nvari", "grado", "tallos", "aporte"]]
    return pd.concat([df_export, df_all_farms], ignore_index=True)[["finca", "nvari", "grado", "aporte"]].copy()


def _generate_qualities_export(fecha_inicio: pd.Timestamp, fecha_fin: pd.Timestamp) -> str:
    source_path = Path(normalize_path(settings.PPROCESADO_OUTPUT_PATH))
    if not source_path.exists():
        raise FileNotFoundError(f"No existe el insumo de calidades: {source_path}")

    df_cal = pd.read_csv(source_path, dtype={"finca": str})
    if df_cal.empty:
        raise RuntimeError("El archivo pprocesado.csv no contiene datos.")

    validate_columns(df_cal, {"fecha", "finca", "bloque", "grado", "fuente", "nvari", "tallos"}, "pprocesado.csv")
    df_cal["fecha"] = pd.to_datetime(df_cal["fecha"], errors="coerce").dt.normalize()
    df_cal = df_cal.dropna(subset=["fecha"]).copy()
    df_cal = df_cal[(df_cal["fecha"] >= fecha_inicio) & (df_cal["fecha"] <= fecha_fin)].copy()
    if df_cal.empty:
        raise RuntimeError(
            f"No hay datos de calidades entre {fecha_inicio.strftime('%Y-%m-%d')} y {fecha_fin.strftime('%Y-%m-%d')} para procesar."
        )

    if settings.CALIDADES_FUENTE_FILTER:
        df_cal = df_cal[df_cal["fuente"].isin(settings.CALIDADES_FUENTE_FILTER)].copy()
    if df_cal.empty:
        raise RuntimeError(
            f"No hay datos de calidades para las fuentes: {settings.CALIDADES_FUENTE_FILTER}."
        )

    df_cal = df_cal.query("grado != 'CB'").copy()
    if df_cal.empty:
        raise RuntimeError("No quedaron datos de calidades después de excluir grado CB.")

    df_cal = (
        df_cal.groupby(["fecha", "finca", "bloque", "grado", "fuente", "nvari"], as_index=False)["tallos"]
        .sum()
    )

    df_cal["aporte"] = (
        df_cal.groupby(["fecha", "finca", "bloque", "nvari"])["tallos"]
        .transform(lambda values: values / values.sum())
    )

    nal_aporte_max = settings.QUALITIES_PIPELINE_NAL_APORTE_MAX
    df_nal = df_cal.query(
        "grado == 'NAL' and aporte <= @nal_aporte_max"
    )[["finca", "fecha", "bloque", "nvari"]]
    df_cal = pd.merge(df_cal, df_nal, on=["finca", "fecha", "bloque", "nvari"], how="inner")
    if df_cal.empty:
        raise RuntimeError("No quedaron registros al aplicar el filtro NAL <= 50%.")

    df_export = _build_qualities_export_rows(df_cal)

    output_path = Path(normalize_path(settings.CALIDADES_OUTPUT_PATH))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_export.to_csv(output_path, index=False, encoding="utf-8-sig")
    return str(output_path)


def generate_qualities_pipeline(params: dict | None = None) -> str:
    fecha_inicio, fecha_fin = resolve_date_range_params(params)
    qualities_output = _generate_qualities_export(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
    return f"csv:{qualities_output}"