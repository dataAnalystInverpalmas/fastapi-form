from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.core.settings import settings
from app.services.utils.dbf_reader import normalize_path
from app.services.etl.helpers import dataframe_to_sql, save_snapshot
from app.services.etl_jobs.production_pipeline_generator import (
    FIRST_CYCLE_MAX_AGE,
    MAX_PRODUCTION_AGE,
    generate_production_pipeline,
)

DETAIL_GROUP_COLUMNS = ["finca", "bloque", "nvariedad", "cosecha", "ciclo"]
CYCLE_END_AGE = {1: FIRST_CYCLE_MAX_AGE, 2: MAX_PRODUCTION_AGE}
HISTORICO_TABLE = "desviacion_produccion_historico"


def _load_detail_curves() -> pd.DataFrame:
    detail_path = Path(normalize_path(settings.CURVAS_PRODUCCION_OUTPUT_PATH))
    if not detail_path.exists():
        generate_production_pipeline()
    if not detail_path.exists():
        raise FileNotFoundError(
            "No existe el detalle de curvas de produccion y no se pudo regenerar automaticamente."
        )

    df = pd.read_excel(detail_path)
    required = {"finca", "bloque", "nvariedad", "cosecha", "ciclo", "edad", "f_m"}
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(f"El detalle de curvas no tiene las columnas esperadas: {sorted(missing)}")

    df["finca"] = df["finca"].astype(str)
    df["nvariedad"] = df["nvariedad"].astype(str)
    df["cosecha"] = df["cosecha"].astype(str)
    df["ciclo"] = pd.to_numeric(df["ciclo"], errors="coerce")
    df["edad"] = pd.to_numeric(df["edad"], errors="coerce")
    df["f_m"] = pd.to_numeric(df["f_m"], errors="coerce")
    return df.dropna(subset=["ciclo", "edad", "f_m"])


def _load_reference_curves() -> pd.DataFrame:
    filtered_path = Path(normalize_path(settings.CURVAS_PRODUCCION_FILTRADA_OUTPUT_PATH))
    if not filtered_path.exists():
        generate_production_pipeline()
    if not filtered_path.exists():
        raise FileNotFoundError(
            "No existe la curva filtrada de referencia y no se pudo regenerar automaticamente."
        )

    df = pd.read_csv(filtered_path, converters={"finca": str, "nvariedad": str})
    df["ciclo"] = pd.to_numeric(df["ciclo"], errors="coerce")
    df["edad"] = pd.to_numeric(df["edad"], errors="coerce")
    df["fm_suave"] = pd.to_numeric(df["fm_suave"], errors="coerce").clip(lower=0)
    df = df.dropna(subset=["ciclo", "edad"])

    df = df.sort_values(["finca", "nvariedad", "ciclo", "edad"])
    df["fm_suave_cum"] = df.groupby(["finca", "nvariedad", "ciclo"])["fm_suave"].cumsum()
    return df


def _reference_lookup(df_ref: pd.DataFrame) -> dict[tuple[str, str, int], tuple[np.ndarray, np.ndarray]]:
    return {
        (finca, nvariedad, int(ciclo)): (
            grupo["edad"].to_numpy(dtype=float),
            grupo["fm_suave_cum"].to_numpy(dtype=float),
        )
        for (finca, nvariedad, ciclo), grupo in df_ref.groupby(["finca", "nvariedad", "ciclo"])
    }


def _equivalent_age(cum_real: float, edades: np.ndarray, acumulado: np.ndarray) -> float:
    """Edad de la curva de referencia en la que se alcanza cum_real (interpolacion inversa)."""
    if acumulado[-1] <= 0 or cum_real >= acumulado[-1]:
        return float(edades[-1])
    if cum_real <= acumulado[0]:
        return float(edades[0])
    return float(np.interp(cum_real, acumulado, edades))


def _classify_estado(semanas_diff: float, umbral: float) -> str:
    if semanas_diff > umbral:
        return "Atrasada"
    if semanas_diff < -umbral:
        return "Adelantada"
    return "Normal"


def _build_desviacion(df_detail: pd.DataFrame, df_ref: pd.DataFrame, umbral: float) -> pd.DataFrame:
    referencias = _reference_lookup(df_ref)

    filas: list[dict] = []
    for keys, grupo in df_detail.groupby(DETAIL_GROUP_COLUMNS, dropna=False, sort=False):
        finca, bloque, nvariedad, cosecha, ciclo = keys
        ciclo_int = int(ciclo)
        edad_actual = float(grupo["edad"].max())
        cum_real = float(grupo["f_m"].sum())
        en_curso = bool(edad_actual < CYCLE_END_AGE.get(ciclo_int, MAX_PRODUCTION_AGE))

        referencia = referencias.get((finca, nvariedad, ciclo_int))
        if referencia is None:
            filas.append(
                {
                    "finca": finca,
                    "bloque": bloque,
                    "nvariedad": nvariedad,
                    "cosecha": cosecha,
                    "ciclo": ciclo_int,
                    "edad_actual": edad_actual,
                    "f_m_acumulado_real": round(cum_real, 4),
                    "f_m_acumulado_esperado": None,
                    "edad_equivalente_curva": None,
                    "semanas_adelanto_atraso": None,
                    "desviacion_pct": None,
                    "estado": "Sin referencia",
                    "en_curso": en_curso,
                }
            )
            continue

        edades_ref, acumulado_ref = referencia
        cum_esperado = float(np.interp(edad_actual, edades_ref, acumulado_ref))
        edad_equivalente = _equivalent_age(cum_real, edades_ref, acumulado_ref)
        semanas_diff = round(edad_actual - edad_equivalente, 2)
        desviacion_pct = round((cum_real - cum_esperado) / cum_esperado * 100, 2) if cum_esperado > 0 else None

        filas.append(
            {
                "finca": finca,
                "bloque": bloque,
                "nvariedad": nvariedad,
                "cosecha": cosecha,
                "ciclo": ciclo_int,
                "edad_actual": edad_actual,
                "f_m_acumulado_real": round(cum_real, 4),
                "f_m_acumulado_esperado": round(cum_esperado, 4),
                "edad_equivalente_curva": round(edad_equivalente, 2),
                "semanas_adelanto_atraso": semanas_diff,
                "desviacion_pct": desviacion_pct,
                "estado": _classify_estado(semanas_diff, umbral),
                "en_curso": en_curso,
            }
        )

    resultado = pd.DataFrame(filas)
    if resultado.empty:
        return resultado
    return resultado.sort_values(["finca", "nvariedad", "bloque", "cosecha", "ciclo"]).reset_index(drop=True)


def _current_snapshot_date() -> date:
    """Lunes de la semana en curso: alinea el snapshot con la cadencia semanal de f_m."""
    today = date.today()
    return today - timedelta(days=today.weekday())


def generate_desviacion_produccion(params: dict | None = None) -> str:
    params = params or {}
    umbral = float(params.get("umbral_semanas", settings.DESVIACION_PRODUCCION_UMBRAL_SEMANAS))

    df_detail = _load_detail_curves()
    df_ref = _load_reference_curves()
    resultado = _build_desviacion(df_detail, df_ref, umbral)
    if resultado.empty:
        raise RuntimeError("No se generaron filas de desviacion de produccion.")

    output_path = Path(normalize_path(settings.DESVIACION_PRODUCCION_OUTPUT_PATH))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    resultado.to_csv(output_path, index=False, encoding="utf-8-sig")

    dataframe_to_sql(resultado, "desviacion_produccion", if_exists="replace")
    save_snapshot(resultado, HISTORICO_TABLE, "fecha_corte", _current_snapshot_date())

    return str(output_path)
