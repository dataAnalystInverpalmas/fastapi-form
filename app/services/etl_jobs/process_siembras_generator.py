from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.settings import settings
from app.services.utils.date_service import ajustar_a_jueves
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
    WHERE p.plantas > 1
    """

    sql_variedades = """
    SELECT
        v.nombre AS variedad, c.nombre AS color, c.orden
    FROM ld_variedades AS v
    LEFT JOIN ld_colores AS c ON c.codigo = v.codgcol
    WHERE v.codflor IN ('CLA', 'CM0')
    """

    sql_real = """
    SELECT
        h.variedad,
        h.fecha_siembra,
        s.cod_temporada AS cosecha,
        h.tipo_siembra AS tsiembra,
        s.año AS programa,
        SUM(plantas) AS plantas
    FROM hplane AS h
    INNER JOIN seasons AS s
      ON s.nombre = h.temporada
    WHERE s.año >= 2024
    GROUP BY h.variedad, h.fecha_siembra, cosecha, tsiembra, programa
    """

    sql_fechas = "SELECT fecha, aass, semana, mes, año FROM dates WHERE dia_semana = 4"

    df_fechas = pd.DataFrame(execute_query(sql_fechas) or [], columns=["fecha", "aass", "semana", "mes", "año"])
    if df_fechas.empty:
        raise RuntimeError("No se encontraron fechas jueves en la tabla dates.")
    df_fechas["aass"] = df_fechas["aass"].astype(str)
    df_fechas["fecha"] = pd.to_datetime(df_fechas["fecha"])

    df_budget = pd.DataFrame(execute_query(select_query) or [], columns=[
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
    df_variedades = pd.DataFrame(execute_query(sql_variedades) or [], columns=["variedad", "color", "orden"])
    df_real = pd.DataFrame(execute_query(sql_real) or [], columns=["variedad", "fecha_siembra", "cosecha", "tsiembra", "programa", "plantas"])

    if df_budget.empty and df_real.empty:
        raise RuntimeError("No se encontraron registros para procesar siembras.")

    df_budget["fecha_siembra"] = pd.to_datetime(df_budget["fecha_siembra"], errors="coerce").apply(ajustar_a_jueves)
    df_real["fecha_siembra"] = pd.to_datetime(df_real["fecha_siembra"], errors="coerce").apply(ajustar_a_jueves)
    df_budget["tipo"] = "teo"
    df_real["tipo"] = "real"

    results = pd.concat([df_real, df_budget], axis=0, ignore_index=True)
    if results.empty:
        raise RuntimeError("No se pudo consolidar informacion de siembras.")

    results["ncamas"] = pd.to_numeric(results["plantas"], errors="coerce").fillna(0) / 960
    results["ncamas"] = pd.to_numeric(results["ncamas"], errors="coerce").round(1)

    results = pd.merge(results, df_variedades, how="left", on="variedad")
    results["fecha_siembra"] = pd.to_datetime(results["fecha_siembra"], errors="coerce")

    results = pd.merge(
        results,
        df_fechas.rename(columns={"fecha": "fecha_siembra"}),
        on="fecha_siembra",
        how="left",
    )

    if results["fecha_siembra"].isna().all():
        raise RuntimeError("No se pudieron normalizar las fechas de siembra.")

    output_path = Path(settings.PROCESS_SIEMBRAS_OUTPUT_PATH)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    results.to_excel(output_path, index=False)
    return str(output_path)