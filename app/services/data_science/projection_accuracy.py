"""Prototipo: precision de las proyecciones de produccion.

Compara, sobre ``quipus_vs_proy``, la proyeccion inicial, la proyeccion
ajustada de Inverpalmas y la proyeccion de Quipus contra la produccion real.
Solo se evaluan filas con produccion real reportada, para no castigar semanas
futuras que todavia no tienen corte.

Metricas:
- WAPE = sum(|proy - real|) / sum(real)  (error absoluto ponderado)
- Sesgo = (sum(proy) - sum(real)) / sum(real)  (> 0 sobreestima, < 0 subestima)
"""
from __future__ import annotations

import pandas as pd

from app.services.data_science.common import read_sql, records, ttl_cache

SOURCES = {
    "proy_inicial": "Proyección inicial",
    "proy_ajustada": "Proyección ajustada",
    "quipus": "Quipus",
}


def _load(flor: str | None, finca: str | None) -> pd.DataFrame:
    where = ["`inverpalmas-real` IS NOT NULL"]
    params: list = []
    if flor:
        where.append("flor = %s")
        params.append(flor)
    if finca:
        where.append("finca = %s")
        params.append(finca)
    sql = f"""
        SELECT finca, flor, variedad, sem_prod,
               `inverpalmas-proy-inicial` AS proy_inicial,
               `inverpalmas-proyección` AS proy_ajustada,
               `quipus-proyección`     AS quipus,
               `inverpalmas-real`          AS real_
        FROM quipus_vs_proy
        WHERE {' AND '.join(where)}
    """
    df = read_sql(sql, params)
    for col in ["proy_inicial", "proy_ajustada", "quipus", "real_"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _metrics(df: pd.DataFrame, source: str) -> dict:
    sub = df[df[source].notna()]
    real = sub["real_"].sum()
    if sub.empty or real <= 0:
        return {"fuente": source, "nombre": SOURCES[source], "filas": 0, "wape": None, "sesgo": None, "real": 0, "proy": 0}
    proy = sub[source].sum()
    return {
        "fuente": source,
        "nombre": SOURCES[source],
        "filas": int(len(sub)),
        "real": float(real),
        "proy": float(proy),
        "wape": float((sub[source] - sub["real_"]).abs().sum() / real),
        "sesgo": float((proy - real) / real),
    }


@ttl_cache()
def projection_accuracy(flor: str | None = None, finca: str | None = None, top: int = 15) -> dict:
    df = _load(flor, finca)
    if df.empty:
        return {"resumen": [], "semanal": [], "variedades": [], "filtros": {"flor": flor, "finca": finca}}

    resumen = [_metrics(df, source) for source in SOURCES]

    semanal = (
        df.groupby("sem_prod", as_index=False)[["real_", "proy_inicial", "proy_ajustada", "quipus"]]
        .sum(min_count=1)
        .sort_values("sem_prod")
    )
    semanal["error_pct"] = (semanal["proy_ajustada"] - semanal["real_"]) / semanal["real_"].where(semanal["real_"] > 0)

    df["abs_err"] = (df["proy_ajustada"] - df["real_"]).abs()
    variedades = (
        df.groupby(["flor", "variedad"], as_index=False)
        .agg(real=("real_", "sum"), proy=("proy_ajustada", "sum"), abs_err=("abs_err", "sum"), semanas=("sem_prod", "nunique"))
    )
    variedades = variedades[variedades["real"] > 0]
    variedades["wape"] = variedades["abs_err"] / variedades["real"]
    variedades["sesgo"] = (variedades["proy"] - variedades["real"]) / variedades["real"]
    # Ordenar por error absoluto en tallos: prioriza donde el error cuesta mas, no solo el % mas alto.
    variedades = variedades.sort_values("abs_err", ascending=False).head(top)

    return {
        "filtros": {"flor": flor, "finca": finca},
        "resumen": resumen,
        "semanal": records(semanal.rename(columns={"real_": "real"})),
        "variedades": records(variedades),
    }
