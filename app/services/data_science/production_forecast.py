"""Prototipo: pronostico estadistico de produccion semanal.

Modelo base deliberadamente simple y explicable (descomposicion multiplicativa):

    pronostico(semana) = nivel_actual x indice_estacional(semana ISO)

- ``indice_estacional``: mediana, por semana ISO, de la razon produccion /
  media movil centrada de 52 semanas en los ultimos anios. Captura los picos
  de fiestas (San Valentin, Madres...) que se repiten cada anio.
- ``nivel_actual``: promedio desestacionalizado de las ultimas 8 semanas.

La precision se mide con un backtest de origen movil: se "viaja al pasado",
se pronostican las siguientes semanas sin ver el futuro y se compara contra lo
real. El mismo backtest se corre para un ingenuo estacional (misma semana del
anio anterior) que sirve de linea base: si el modelo no le gana, no sirve.
La banda de incertidumbre sale de los errores observados en ese backtest.

La produccion real viene de ``ld_lonas``; la proyeccion ajustada oficial
(``ld_proyecciones`` tipo ``AJ``) se muestra al lado para comparar.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from app.services.data_science.common import read_sql, records, ttl_cache

SEASON = 52
LEVEL_WEEKS = 8
HISTORY_YEARS = 4
BACKTEST_ORIGINS = 8


def _weekly_production(flor: str, finca: str | None) -> pd.Series:
    where = ["flor = %s"]
    params: list = [flor]
    if finca:
        where.append("finca = %s")
        params.append(finca)
    sql = f"""
        SELECT DATE_SUB(DATE(fecha), INTERVAL WEEKDAY(fecha) DAY) AS semana,
               SUM(tallos) AS tallos,
               MAX(DATE(fecha)) AS ultimo_dia
        FROM ld_lonas
        WHERE {' AND '.join(where)}
          AND fecha >= DATE_SUB(CURDATE(), INTERVAL {HISTORY_YEARS + 1} YEAR)
        GROUP BY semana
        ORDER BY semana
    """
    df = read_sql(sql, params)
    if df.empty:
        return pd.Series(dtype=float)
    df["semana"] = pd.to_datetime(df["semana"])
    # La ultima semana suele estar incompleta (se carga a diario): se descarta
    # si no llega hasta el sabado, para no confundir "falta cargar" con "cayo la produccion".
    last = df.iloc[-1]
    if pd.to_datetime(last["ultimo_dia"]) < last["semana"] + timedelta(days=5):
        df = df.iloc[:-1]
    series = df.set_index("semana")["tallos"].astype(float)
    full_index = pd.date_range(series.index.min(), series.index.max(), freq="W-MON")
    return series.reindex(full_index, fill_value=0.0)


def _official_projection(flor: str, finca: str | None, desde: pd.Timestamp) -> pd.Series:
    where = ["flor = %s", "tipo = 'AJ'", "fecha >= %s"]
    params: list = [flor, desde.date()]
    if finca:
        where.append("finca = %s")
        params.append(finca)
    sql = f"""
        SELECT DATE_SUB(DATE(fecha), INTERVAL WEEKDAY(fecha) DAY) AS semana, SUM(tallos) AS tallos
        FROM ld_proyecciones
        WHERE {' AND '.join(where)}
        GROUP BY semana
    """
    df = read_sql(sql, params)
    if df.empty:
        return pd.Series(dtype=float)
    df["semana"] = pd.to_datetime(df["semana"])
    return df.set_index("semana")["tallos"].astype(float)


def _iso_week(index: pd.DatetimeIndex) -> np.ndarray:
    weeks = index.isocalendar().week.to_numpy().astype(int)
    return np.minimum(weeks, SEASON)  # la semana 53 se trata como la 52


def _seasonal_index(series: pd.Series) -> pd.Series:
    # Media movil centrada 2x52: tendencia sin estacionalidad.
    trend = series.rolling(SEASON, center=True, min_periods=SEASON // 2).mean()
    trend = trend.rolling(2, min_periods=1).mean()
    ratio = (series / trend.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    by_week = ratio.groupby(_iso_week(series.index)).median()
    by_week = by_week.reindex(range(1, SEASON + 1)).interpolate(limit_direction="both").fillna(1.0)
    return by_week / by_week.mean()


def _fit_predict(history: pd.Series, horizon: int) -> pd.Series:
    index = _seasonal_index(history)
    recent = history.iloc[-LEVEL_WEEKS:]
    recent_idx = index.loc[_iso_week(recent.index)].to_numpy()
    level = float(np.mean(recent.to_numpy() / np.where(recent_idx > 0, recent_idx, 1.0)))
    future = pd.date_range(history.index[-1] + timedelta(weeks=1), periods=horizon, freq="W-MON")
    return pd.Series(level * index.loc[_iso_week(future)].to_numpy(), index=future)


def _seasonal_naive(history: pd.Series, horizon: int) -> pd.Series:
    future = pd.date_range(history.index[-1] + timedelta(weeks=1), periods=horizon, freq="W-MON")
    values = [history.get(day - timedelta(weeks=SEASON), np.nan) for day in future]
    return pd.Series(values, index=future, dtype=float)


def _backtest(series: pd.Series, horizon: int) -> dict:
    model_errors, naive_abs, model_abs, actual_sum = [], 0.0, 0.0, 0.0
    min_history = SEASON * 2 + LEVEL_WEEKS
    origins = [len(series) - horizon - step * 4 for step in range(BACKTEST_ORIGINS)]
    origins = [o for o in origins if o >= min_history]
    for origin in origins:
        history, actual = series.iloc[:origin], series.iloc[origin:origin + horizon]
        pred = _fit_predict(history, horizon).reindex(actual.index)
        naive = _seasonal_naive(history, horizon).reindex(actual.index)
        model_abs += float((pred - actual).abs().sum())
        naive_abs += float((naive - actual).abs().sum())
        actual_sum += float(actual.sum())
        valid = actual > 0
        model_errors.extend(((actual[valid] - pred[valid]) / pred[valid]).tolist())
    if not origins or actual_sum <= 0:
        return {"origenes": 0, "wape_modelo": None, "wape_ingenuo": None, "q10": -0.2, "q90": 0.2}
    errors = np.array(model_errors)
    return {
        "origenes": len(origins),
        "wape_modelo": model_abs / actual_sum,
        "wape_ingenuo": naive_abs / actual_sum,
        "q10": float(np.quantile(errors, 0.10)),
        "q90": float(np.quantile(errors, 0.90)),
    }


@ttl_cache()
def production_forecast(flor: str = "CLA", finca: str | None = None, horizonte: int = 12) -> dict:
    horizonte = max(4, min(int(horizonte), 26))
    series = _weekly_production(flor, finca)
    if len(series) < SEASON * 2 + LEVEL_WEEKS:
        return {"error": "Historia insuficiente: se necesitan al menos 2 años de producción semanal.", "historia": records(series.rename("real").reset_index().rename(columns={"index": "semana"}))}

    backtest = _backtest(series, horizonte)
    forecast = _fit_predict(series, horizonte)
    official = _official_projection(flor, finca, series.index[-SEASON])

    future = pd.DataFrame({
        "semana": forecast.index,
        "pronostico": forecast.to_numpy(),
        "banda_baja": (forecast * (1 + backtest["q10"])).clip(lower=0).to_numpy(),
        "banda_alta": (forecast * (1 + backtest["q90"])).to_numpy(),
        "proy_oficial": official.reindex(forecast.index).to_numpy(),
    })
    history = series.iloc[-SEASON:].rename("real").to_frame()
    history["proy_oficial"] = official.reindex(history.index)
    history = history.reset_index().rename(columns={"index": "semana"})

    index = _seasonal_index(series)
    peaks = index.sort_values(ascending=False).head(5)

    return {
        "filtros": {"flor": flor, "finca": finca, "horizonte": horizonte},
        "historia": records(history, 0),
        "pronostico": records(future, 0),
        "backtest": backtest,
        "semanas_pico": [{"semana_iso": int(w), "indice": round(float(v), 3)} for w, v in peaks.items()],
        "total_pronostico": float(forecast.sum()),
        "total_oficial": float(official.reindex(forecast.index).sum()) if not official.empty else None,
    }
