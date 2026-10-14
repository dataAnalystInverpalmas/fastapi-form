"""Prototipo: riesgo de fusarium por lote.

Usa la ultima evaluacion de cada lote (``ld_fusarium.ultimo = 1``):

1. Tasas historicas por variedad y por sustrato, con encogimiento hacia la
   tasa de la flor para que variedades con pocos lotes no aparezcan como las
   peores (o mejores) por azar.
2. Un clasificador (gradient boosting) que estima la probabilidad de que un
   lote termine con fusarium alto (>= ``HIGH_THRESHOLD`` % de matas). Se
   entrena con lotes ya erradicados y se valida en el tiempo: entrena con los
   lotes mas antiguos y se evalua en los mas recientes, como se usaria en la
   practica. Luego puntua los lotes que siguen sembrados.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score

from app.services.data_science.common import read_sql, records, ttl_cache

HIGH_THRESHOLD = 10.0
PRIOR_PLANTS = 20000
FEATURES = ["flor", "finca", "variedad", "sustrato", "pico", "matas"]
CATEGORICAL = ["flor", "finca", "variedad", "sustrato", "pico"]


def _load() -> pd.DataFrame:
    df = read_sql(
        """
        SELECT finca, flor, bloque, cosecha, nvari AS variedad, fecha, sustrato, pico,
               porc, estadoact, matas, matfus
        FROM ld_fusarium
        WHERE ultimo = 1 AND matas > 0
        """
    )
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["sustrato"] = df["sustrato"].fillna("").str.strip().replace("", "SIN DATO")
    df["pico"] = df["pico"].astype(str)
    df["alto"] = (df["porc"] >= HIGH_THRESHOLD).astype(int)
    return df


def _shrunk_rates(df: pd.DataFrame, by: str, min_lots: int = 3) -> pd.DataFrame:
    flor_rate = df.groupby("flor")["matfus"].sum() / df.groupby("flor")["matas"].sum()
    grouped = df.groupby(["flor", by], as_index=False).agg(
        lotes=("matas", "size"), matas=("matas", "sum"), matfus=("matfus", "sum"), pct_alto=("alto", "mean")
    )
    grouped = grouped[grouped["lotes"] >= min_lots]
    prior = grouped["flor"].map(flor_rate)
    grouped["tasa"] = grouped["matfus"] / grouped["matas"]
    grouped["tasa_ajustada"] = (grouped["matfus"] + PRIOR_PLANTS * prior) / (grouped["matas"] + PRIOR_PLANTS)
    grouped["tasa_flor"] = prior
    return grouped.sort_values("tasa_ajustada", ascending=False)


def _encode(df: pd.DataFrame, categories: dict[str, list]) -> pd.DataFrame:
    x = df[FEATURES].copy()
    for col in CATEGORICAL:
        x[col] = pd.Categorical(x[col], categories=categories[col]).codes.astype(float)
        x.loc[x[col] < 0, col] = np.nan  # categoria nunca vista en entrenamiento
    return x


def _model(df: pd.DataFrame) -> dict:
    closed = df[df["estadoact"] == "Erradicado"].sort_values("fecha")
    active = df[df["estadoact"] != "Erradicado"]
    if len(closed) < 500 or closed["alto"].nunique() < 2:
        return {"disponible": False, "motivo": "Pocos lotes cerrados para entrenar."}

    cut = int(len(closed) * 0.8)
    train, test = closed.iloc[:cut], closed.iloc[cut:]
    categories = {col: sorted(train[col].astype(str).unique()) for col in CATEGORICAL}
    for frame in (train, test, active, closed):
        for col in CATEGORICAL:
            frame.loc[:, col] = frame[col].astype(str)

    def build():
        return HistGradientBoostingClassifier(
            categorical_features=[FEATURES.index(c) for c in CATEGORICAL],
            max_depth=4, learning_rate=0.05, max_iter=300, random_state=42,
        )

    clf = build().fit(_encode(train, categories), train["alto"])
    x_test = _encode(test, categories)
    proba = clf.predict_proba(x_test)[:, 1]
    auc = roc_auc_score(test["alto"], proba) if test["alto"].nunique() > 1 else None

    importance = permutation_importance(clf, x_test, test["alto"], scoring="roc_auc", n_repeats=5, random_state=42)
    importancia = sorted(
        ({"variable": f, "importancia": float(v)} for f, v in zip(FEATURES, importance.importances_mean)),
        key=lambda item: item["importancia"], reverse=True,
    )

    # Reentrena con todos los lotes cerrados para puntuar los activos.
    categories_all = {col: sorted(closed[col].astype(str).unique()) for col in CATEGORICAL}
    final = build().fit(_encode(closed, categories_all), closed["alto"])
    scored = active.copy()
    if not scored.empty:
        scored["prob_alto"] = final.predict_proba(_encode(scored, categories_all))[:, 1]
        scored = scored.sort_values("prob_alto", ascending=False)

    return {
        "disponible": True,
        "lotes_entrenamiento": int(len(train)),
        "lotes_prueba": int(len(test)),
        "corte_fecha": train["fecha"].max().date().isoformat(),
        "tasa_base": float(test["alto"].mean()),
        "auc": float(auc) if auc is not None else None,
        "importancia": importancia,
        "lotes_activos": records(
            scored[["finca", "flor", "bloque", "cosecha", "variedad", "sustrato", "matas", "porc", "prob_alto"]].head(30)
        ) if not scored.empty else [],
    }


@ttl_cache()
def fusarium_risk(flor: str | None = None) -> dict:
    df = _load()
    if flor:
        df = df[df["flor"] == flor]
    if df.empty:
        return {"filtros": {"flor": flor}, "variedades": [], "sustratos": [], "modelo": {"disponible": False}}
    return {
        "filtros": {"flor": flor},
        "umbral_alto": HIGH_THRESHOLD,
        "resumen": {
            "lotes": int(len(df)),
            "tasa_global": float(df["matfus"].sum() / df["matas"].sum()),
            "pct_lotes_alto": float(df["alto"].mean()),
        },
        "variedades": records(_shrunk_rates(df, "variedad").head(20)),
        "sustratos": records(_shrunk_rates(df, "sustrato", min_lots=10)),
        "modelo": _model(df.copy()),
    }
