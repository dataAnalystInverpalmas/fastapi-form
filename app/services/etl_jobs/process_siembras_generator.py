from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.settings import settings
from app.services.etl.helpers import execute_query


def generate_process_siembras_report() -> str:
    select_query = """
    SELECT
        p.finca, p.bloque, p.nave, p.tabla, p.cama, p.variedad,
        d.aass AS fecha_siembra, p.plantas, p.nmanguera, p.tipo_suelo,
        p.ferradica AS fecha_arranque,
        CASE
            WHEN p.tipo_siembra = '1PICO' THEN 1
            WHEN p.tipo_siembra = 'REEMPLAZO' THEN 1
            ELSE 2
        END AS ciclos
    FROM plane AS p
    LEFT JOIN dates AS d ON d.fecha = p.fecha_siembra
    WHERE p.plantas > 1 AND p.producto IN('CLAVEL','MINICLAVEL')
    """

    results = pd.DataFrame(execute_query(select_query) or [], columns=[
        "finca",
        "bloque",
        "nave",
        "tabla",
        "cama",
        "variedad",
        "fecha_siembra",
        "plantas",
        "nmanguera",
        "tipo_suelo",
        "fecha_arranque",
        "ciclos",
    ])

    if results.empty:
        raise RuntimeError("No se encontraron registros para procesar siembras.")

    filter_mask = ~(
        (results["finca"] == "INVERPALMAS")
        & (results["bloque"] == 16)
        & (results["nave"] == 10)
        & (results["variedad"] != "MISS TRENDY")
    )

    results = results[filter_mask]

    if results.empty:
        raise RuntimeError("No se encontraron registros para procesar siembras.")

    results["fecha_arranque"] = results["fecha_arranque"].astype(str).str[:]
    results["fecha_siembra"] = (
        results["fecha_siembra"].astype("string")
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(4)
        .str.slice(0, 4)
    )
    results["tipo_suelo"] = results["tipo_suelo"].astype(str).str.replace(" ", "_")
    results["ciclos"] = results["ciclos"].astype(str).str[:]

    cascarilla_map = {
        "CASCARILLA_PRIMER_USO": "NNUEVA",
        "CASCARILLA_SEGUNDO_USO": "2SEGUNDO_USO",
        "CASCARILLA_TERCER_USO": "3TERCER_USO",
        "CASCARILLA_CUARTO_USO": "4CUARTO_USO",
    }

    goteo_map = {
        "Gotero Externo (2.0 l/h - 0.3m)": "GOTERO_EXTERNO_(2.0_L/H_-_0.3M)",
        "Gotero Interno (1.2 l/h - 0.2m)": "GOTERO_INTERNO_(1.2_L/H_-_0.2M)",
        "Gotero Externo (2.0 l/h - 0.2m)": "GOTERO_EXTERNO_(2.0_L/H_-_0.2M)",
        "Gotero Interno (1.0 l/h - 0.2m)": "GOTERO_INTERNO_(1.0_L/H_-_0.2M)",
    }

    results["goteo"] = results["nmanguera"].map(goteo_map).fillna("GOTERO_EXTERNO_(1.0_L/H_-_0.2M)")
    results["cascarilla"] = results["tipo_suelo"].map(cascarilla_map).fillna("NNUEVA")
    
    results["semana"] = results["fecha_siembra"].str[-2:].str.zfill(2)
    results["año"] = "20" + results["fecha_siembra"].str[:2]

    # Final column selection and renaming
    final_df = results[[
        "finca", "bloque", "nave", "tabla", "cama", "variedad",
        "semana", "año", "plantas", "ciclos", "cascarilla", "goteo"
    ]].rename(columns={
        "plantas": "cantidad",
        "ciclos": "ciclo",
    })

    output_path = Path(settings.PROCESS_SIEMBRAS_OUTPUT_PATH)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_df.to_excel(output_path, index=False)
    return str(output_path)