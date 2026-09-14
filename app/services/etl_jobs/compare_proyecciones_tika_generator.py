from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from app.core.settings import settings
from app.services.utils.dbf_reader import normalize_path
from app.services.etl_jobs.compare_tika_produccion_generator import (
    _load_dates_and_variedades,
    _process_tika_projection,
)


def _resolve_modelos_tika(params: dict[str, Any] | None) -> list[int]:
    raw_values = list((params or {}).get("modelos_tika") or [])
    parsed = [int(value) for value in raw_values if str(value).strip()]
    return parsed or list(settings.COMPARE_PROYECCIONES_TIKA_DEFAULT_MODELS)


def generate_compare_proyecciones_tika_report(params: dict[str, Any] | None = None) -> str:
    """Compara las proyecciones (proy1/2/3.csv) de varios modelos/escenarios Tika.

    A diferencia de 'compare_tika_produccion_despachos' (que solo compara 4
    modelos fijos contra despachos/demanda/quipus), este job acepta una
    lista libre de modelos_tika y produce solo el formato largo
    (fecha, flor, variedad, color, tallos, tipo) con tipo='Tika_<modelo>',
    pensado para comparar escenarios entre si.
    """
    modelos_tika = _resolve_modelos_tika(params)
    df_dates, df_vari = _load_dates_and_variedades()

    frames = [
        _process_tika_projection(modelo_tika, f"Tika_{modelo_tika}", df_dates, df_vari)
        for modelo_tika in modelos_tika
    ]
    df = pd.concat(frames, axis=0, ignore_index=True)

    output_csv = Path(normalize_path(settings.COMPARE_PROYECCIONES_TIKA_OUTPUT_PATH))
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    output_excel = Path(normalize_path(settings.COMPARE_PROYECCIONES_TIKA_OUTPUT_EXCEL_PATH))
    output_excel.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(output_excel, index=False)

    return str(output_csv)
