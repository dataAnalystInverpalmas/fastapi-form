"""Prototipo: deteccion de bloques con calidad anomala (exceso de nacional).

En ``ld_producto_procesado`` los grados SEL/FAN/STD/SHR/CB son exportables y
``NAL`` es flor nacional (perdida de valor). Para cada finca-bloque-variedad
en la ventana reciente se compara su % de nacional contra el de la misma
variedad en toda la empresa.

Los bloques con pocos tallos tienen porcentajes muy ruidosos, asi que se usa
encogimiento empirico-bayesiano: la tasa del bloque se "jala" hacia la tasa de
la variedad con un peso equivalente a ``PRIOR_STEMS`` tallos. Asi un bloque
solo se marca cuando hay evidencia suficiente, no por azar.
"""
from __future__ import annotations

import pandas as pd

from app.services.data_science.common import read_sql, records, ttl_cache

PRIOR_STEMS = 2000
ALERT_RATIO = 1.5
MIN_EXCESS_STEMS = 500


@ttl_cache()
def quality_anomalies(flor: str | None = None, semanas: int = 8, top: int = 25) -> dict:
    semanas = max(2, min(int(semanas), 26))
    where = ["fecha >= DATE_SUB((SELECT MAX(fecha) FROM ld_producto_procesado), INTERVAL %s WEEK)"]
    params: list = [semanas]
    if flor:
        where.append("flor = %s")
        params.append(flor)
    sql = f"""
        SELECT finca, CAST(bloque AS SIGNED) AS bloque, flor, nvari AS variedad,
               SUM(tallos) AS total,
               SUM(CASE WHEN grado = 'NAL' THEN tallos ELSE 0 END) AS nal
        FROM ld_producto_procesado
        WHERE {' AND '.join(where)}
        GROUP BY finca, bloque, flor, nvari
    """
    df = read_sql(sql, params)
    if df.empty:
        return {"bloques": [], "tendencia": [], "variedades": [], "filtros": {"flor": flor, "semanas": semanas}}
    df[["total", "nal"]] = df[["total", "nal"]].astype(float)
    df = df[df["total"] > 0]

    var_rates = df.groupby(["flor", "variedad"])[["nal", "total"]].sum()
    var_rates["tasa_variedad"] = var_rates["nal"] / var_rates["total"]
    df = df.merge(var_rates[["tasa_variedad"]].reset_index(), on=["flor", "variedad"])

    df["tasa_bloque"] = df["nal"] / df["total"]
    df["tasa_ajustada"] = (df["nal"] + PRIOR_STEMS * df["tasa_variedad"]) / (df["total"] + PRIOR_STEMS)
    df["razon"] = df["tasa_ajustada"] / df["tasa_variedad"].where(df["tasa_variedad"] > 0)
    df["exceso_tallos"] = df["nal"] - df["total"] * df["tasa_variedad"]
    df["alerta"] = (df["razon"] >= ALERT_RATIO) & (df["exceso_tallos"] >= MIN_EXCESS_STEMS)

    bloques = df.sort_values("exceso_tallos", ascending=False).head(top)

    trend_where = ["fecha >= DATE_SUB((SELECT MAX(fecha) FROM ld_producto_procesado), INTERVAL 104 WEEK)"]
    trend_params: list = []
    if flor:
        trend_where.append("flor = %s")
        trend_params.append(flor)
    tendencia = read_sql(
        f"""
        SELECT DATE_SUB(DATE(fecha), INTERVAL WEEKDAY(fecha) DAY) AS semana,
               SUM(CASE WHEN grado = 'NAL' THEN tallos ELSE 0 END) / SUM(tallos) AS pct_nal,
               SUM(tallos) AS total
        FROM ld_producto_procesado
        WHERE {' AND '.join(trend_where)}
        GROUP BY semana ORDER BY semana
        """,
        trend_params,
    )
    tendencia = tendencia.iloc[:-1] if len(tendencia) > 1 else tendencia  # ultima semana parcial

    total = df[["nal", "total"]].sum()
    return {
        "filtros": {"flor": flor, "semanas": semanas},
        "parametros": {"prior_tallos": PRIOR_STEMS, "razon_alerta": ALERT_RATIO, "exceso_minimo": MIN_EXCESS_STEMS},
        "resumen": {
            "pct_nal": float(total["nal"] / total["total"]) if total["total"] else None,
            "total_tallos": float(total["total"]),
            "bloques_evaluados": int(len(df)),
            "bloques_alerta": int(df["alerta"].sum()),
            "exceso_alerta": float(df.loc[df["alerta"], "exceso_tallos"].sum()),
        },
        "bloques": records(bloques),
        "tendencia": records(tendencia),
    }
