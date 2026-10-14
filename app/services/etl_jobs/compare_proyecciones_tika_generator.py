from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.settings import settings
from app.services.etl.helpers import dataframe_to_sql, validate_columns
from app.services.utils.dbf_reader import normalize_path
from app.services.etl_jobs.compare_tika_produccion_generator import (
    _load_dates_and_variedades,
    _normalize_text,
    _parse_quantity,
    _process_esquejes_futuros,
    _process_salvamento,
    _process_tika_projection,
    _read_tika_csv,
)

logger = logging.getLogger(__name__)


def _resolve_modelos_tika(params: dict[str, Any] | None) -> list[int]:
    raw_values = list((params or {}).get("modelos_tika") or [])
    parsed = [int(value) for value in raw_values if str(value).strip()]
    return parsed or list(settings.COMPARE_PROYECCIONES_TIKA_DEFAULT_MODELS)


def _process_guarde(modelo_tika: int, tipo: str, df_dates: pd.DataFrame, df_vari: pd.DataFrame) -> pd.DataFrame:
    """Tallos en guarde (columna Cantidad de guarde.csv) de un modelo/escenario Tika."""
    path = Path(normalize_path(f"//172.10.18.2/usuarios/Hilder/Data/tika/{modelo_tika}/guarde.csv"))
    if not path.exists():
        raise FileNotFoundError(f"No existe guarde.csv para modelo Tika {modelo_tika}: {path}")
    df = _read_tika_csv(path)
    validate_columns(df, {"semana", "variedad", "cantidad"}, path.name)
    df = pd.merge(
        df.rename(columns={"semana": "aass"}),
        df_dates[["fecha", "aass"]],
        on="aass",
        how="left",
    ).drop(columns=["aass"])
    df["tallos"] = _parse_quantity(df["cantidad"])
    df["variedad"] = _normalize_text(df["variedad"])
    df = pd.merge(df, df_vari, on="variedad", how="left")
    df["tipo"] = tipo
    df = (
        df.groupby(["fecha", "flor", "variedad", "color", "tipo"], dropna=False)["tallos"]
        .sum()
        .reset_index()
    )
    return df[["fecha", "flor", "variedad", "color", "tallos", "tipo"]].copy()


# fuente -> procesador del archivo Tika correspondiente en tika/<modelo>/
FUENTES = {
    "proyecciones": _process_tika_projection,  # proy1/2/3.csv
    "siembras": _process_esquejes_futuros,  # esquejes_futuros.csv
    "rotaciones": _process_salvamento,  # salvamento.csv
    "guardes": _process_guarde,  # guarde.csv
}


def generate_compare_proyecciones_tika_report(params: dict[str, Any] | None = None) -> str:
    """Compara varios modelos/escenarios Tika entre si, por fuente.

    A diferencia de 'compare_tika_produccion_despachos' (que solo compara 4
    modelos fijos contra despachos/demanda/quipus), este job acepta una
    lista libre de modelos_tika y produce solo el formato largo
    (fecha, flor, variedad, color, tallos, tipo, fuente) con
    tipo='Tika_<modelo>' y fuente en proyecciones/siembras/rotaciones/guardes,
    pensado para comparar escenarios entre si. Se guarda en CSV y en la
    tabla MySQL tika_compara_escenarios (se reemplaza en cada corrida).
    """
    modelos_tika = _resolve_modelos_tika(params)
    df_dates, df_vari = _load_dates_and_variedades()

    frames = []
    for fuente, procesar in FUENTES.items():
        for modelo_tika in modelos_tika:
            try:
                frame = procesar(modelo_tika, f"Tika_{modelo_tika}", df_dates, df_vari)
            except FileNotFoundError as exc:
                # Los escenarios viejos no traen todos los archivos (p.ej. sin esquejes_futuros.csv)
                logger.warning("Se omite fuente '%s' del modelo %s: %s", fuente, modelo_tika, exc)
                continue
            frame["fuente"] = fuente
            frames.append(frame)
    if not frames:
        raise FileNotFoundError(f"No se encontro ningun archivo Tika para los modelos {modelos_tika}.")
    df = pd.concat(frames, axis=0, ignore_index=True)

    output_csv = Path(normalize_path(settings.COMPARE_PROYECCIONES_TIKA_OUTPUT_PATH))
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    dataframe_to_sql(df, "tika_compara_escenarios", if_exists="replace")

    return str(output_csv)
