from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from app.core.settings import settings
from app.services.utils.date_service import ajustar_a_jueves
from app.services.utils.dbf_reader import normalize_path
from app.services.etl.helpers import execute_query


def _build_output_path() -> Path:
    output_dir = os.environ.get("DIR_OUTPUTS")
    if output_dir:
        resolved_dir = Path(normalize_path(output_dir))
        if str(resolved_dir).lower().startswith("c:\\users\\"):
            return Path(normalize_path(settings.SIEMBRAS_TEO_REAL_OUTPUT_PATH))
        return resolved_dir / "siembras teo vs real.xlsx"
    return Path(normalize_path(settings.SIEMBRAS_TEO_REAL_OUTPUT_PATH))


def generate_siembras_teo_real() -> str:
    programas = settings.SIEMBRAS_TEO_REAL_ANIOS
    programas_sql = ", ".join(str(int(anio)) for anio in programas)
    anio_inicio = min(programas)
    flores_sql = ", ".join(f"'{flor}'" for flor in settings.SIEMBRAS_TEO_REAL_FLOR_FILTER)

    select_query = f"""
    SELECT
        p.variedad,
        p.fecha_siembra,
        s.cod_temporada AS cosecha,
        p.tipo AS tsiembra,
        p.programa,
        SUM(p.plantas) AS plantas
    FROM program AS p
    INNER JOIN seasons AS s
        ON s.nombre = p.temporada_obj
    WHERE programa IN ({programas_sql}) AND estado = 1
    GROUP BY variedad, fecha_siembra, cosecha, programa, tsiembra
    """

    sql_variedades = f"""
    SELECT
        v.nombre AS variedad, c.nombre AS color, c.orden
    FROM ld_variedades AS v
    LEFT JOIN ld_colores AS c ON c.codigo = v.codgcol
    WHERE v.codflor IN ({flores_sql})
    """

    sql_real = f"""
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
    WHERE s.año >= {anio_inicio}
    GROUP BY h.variedad, h.fecha_siembra, cosecha, tsiembra, programa
    """

    sql_fechas = "SELECT fecha, aass, semana, mes, año FROM dates WHERE dia_semana = 4"

    df_fechas = pd.DataFrame(execute_query(sql_fechas) or [], columns=["fecha", "aass", "semana", "mes", "año"])
    if df_fechas.empty:
        raise RuntimeError("No se encontraron fechas jueves en la tabla dates.")
    df_fechas["aass"] = df_fechas["aass"].astype(str)
    df_fechas["fecha"] = pd.to_datetime(df_fechas["fecha"], errors="coerce")

    df_budget = pd.DataFrame(execute_query(select_query) or [], columns=[
        "variedad",
        "fecha_siembra",
        "cosecha",
        "tsiembra",
        "programa",
        "plantas",
    ])
    df_variedades = pd.DataFrame(execute_query(sql_variedades) or [], columns=["variedad", "color", "orden"])
    df_real = pd.DataFrame(execute_query(sql_real) or [], columns=[
        "variedad",
        "fecha_siembra",
        "cosecha",
        "tsiembra",
        "programa",
        "plantas",
    ])

    if df_budget.empty and df_real.empty:
        raise RuntimeError("No se encontraron registros para procesar siembras teóricas y reales.")

    df_budget["fecha_siembra"] = pd.to_datetime(df_budget["fecha_siembra"], errors="coerce").apply(ajustar_a_jueves)
    df_real["fecha_siembra"] = pd.to_datetime(df_real["fecha_siembra"], errors="coerce").apply(ajustar_a_jueves)
    df_budget["tipo"] = "teo"
    df_real["tipo"] = "real"

    results = pd.concat([df_real, df_budget], axis=0, ignore_index=True)
    if results.empty:
        raise RuntimeError("No se pudo consolidar la informacion de siembras teóricas y reales.")

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

    if results.empty:
        raise RuntimeError("El DataFrame final de siembras teóricas y reales está vacío.")

    output_path = _build_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    results.to_excel(output_path, index=False)
    return str(output_path)