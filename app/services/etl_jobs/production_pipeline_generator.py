from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from app.core.settings import settings
from app.services.utils.dbf_reader import normalize_path
from app.services.etl.helpers import execute_query, resolve_date_range_params
from app.services.utils.curve_functions import curve_ini, curve_values_by_age, datos_curva, rescale_to_total


MAX_PRODUCTION_AGE = 68
FIRST_CYCLE_MAX_AGE = 35
POSITIVE_TOLERANCE = 1e-9

DETAIL_SORT_COLUMNS = ["finca", "bloque", "nvariedad", "cosecha", "ciclo", "edad"]
SUMMARY_SORT_COLUMNS = ["finca", "nvariedad", "ciclo"]
ALL_FARMS_CODE = settings.ALL_FARMS_CODE  # codigo de "todas las fincas consolidadas"
FILTER_COLUMN = "filtro"
MIN_POINTS_CYCLE_1 = 8
MIN_POINTS_CYCLE_2 = 14

DEFAULT_SMOOTHING_PARAMS = {
    "sem_valle": 8,
    "peak_window_weeks": 4,
    "smooth_window_length": 7,
    "smooth_polyorder": 2,
    "force_valley_weeks_after_peak": 8,
}

CURVE_SUMMARY_AGES = np.arange(18, MAX_PRODUCTION_AGE + 1)


def _sort_report_rows(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    sort_columns = [column for column in columns if column in df.columns]
    if not sort_columns:
        return df.reset_index(drop=True)
    return df.sort_values(sort_columns, kind="stable").reset_index(drop=True)


def _asignar_ciclo(edad: int | float) -> float:
    if edad <= FIRST_CYCLE_MAX_AGE:
        return 1
    if edad <= MAX_PRODUCTION_AGE:
        return 2
    return np.nan


def _window_size_for_ciclo(ciclo: int | float) -> int:
    if int(ciclo) == 1:
        return 4
    if int(ciclo) == 2:
        return 10
    return 4


def _keep_strongest_consecutive_run(edades: np.ndarray, valores: np.ndarray) -> np.ndarray:
    valores = np.asarray(valores, dtype=float).copy()
    edades = np.asarray(edades, dtype=int)
    positivos = valores > POSITIVE_TOLERANCE

    if not positivos.any():
        return valores

    runs: list[tuple[int, int, float, int]] = []
    run_start = None

    for index, is_positive in enumerate(positivos):
        if not is_positive:
            if run_start is not None:
                runs.append(
                    (
                        run_start,
                        index,
                        float(valores[run_start:index].sum()),
                        index - run_start,
                    )
                )
                run_start = None
            continue

        if run_start is None:
            run_start = index
            continue

        if edades[index] != edades[index - 1] + 1:
            runs.append(
                (
                    run_start,
                    index,
                    float(valores[run_start:index].sum()),
                    index - run_start,
                )
            )
            run_start = index

    if run_start is not None:
        runs.append(
            (
                run_start,
                len(valores),
                float(valores[run_start:].sum()),
                len(valores) - run_start,
            )
        )

    if len(runs) <= 1:
        return valores

    best_start, best_end, _, _ = max(runs, key=lambda run: (run[2], run[3]))
    filtered = np.zeros_like(valores)
    filtered[best_start:best_end] = valores[best_start:best_end]
    return filtered


def _force_cycle_1_valley_by_peak(
    curva_por_edad: pd.DataFrame,
    peak_cycle_1_age: int | None,
    valley_weeks_after_peak: int,
) -> pd.DataFrame:
    if peak_cycle_1_age is None or valley_weeks_after_peak < 0:
        return curva_por_edad

    ciclo_2_activas = curva_por_edad[
        (curva_por_edad["ciclo"] == 2) & (curva_por_edad["fm_suave"] > POSITIVE_TOLERANCE)
    ]["edad"]
    if ciclo_2_activas.empty:
        return curva_por_edad

    valley_start_age = int(peak_cycle_1_age) + 1
    valley_end_age = min(int(peak_cycle_1_age) + int(valley_weeks_after_peak), int(ciclo_2_activas.min()) - 1)
    if valley_end_age < valley_start_age:
        return curva_por_edad

    valley_mask = (curva_por_edad["edad"] >= valley_start_age) & (curva_por_edad["edad"] <= valley_end_age)
    curva_por_edad.loc[valley_mask, "fm_suave"] = 0.0
    return curva_por_edad


def _enforce_smoothed_curve_rules(
    temp: pd.DataFrame,
    suavizada: np.ndarray,
    peak_cycle_1_age: int | None,
    valley_weeks_after_peak: int,
) -> pd.DataFrame:
    edades = pd.Series(sorted(temp["edad"].astype(int).unique()), name="edad")
    curva_por_edad = pd.DataFrame({"edad": edades})
    curva_por_edad["ciclo"] = curva_por_edad["edad"].apply(_asignar_ciclo)
    curva_por_edad["fm_suave"] = curve_values_by_age(curva_por_edad, suavizada)
    curva_por_edad.loc[curva_por_edad["edad"] > MAX_PRODUCTION_AGE, "fm_suave"] = 0.0

    for ciclo in [1, 2]:
        mask = curva_por_edad["ciclo"] == ciclo
        if not mask.any():
            continue

        edades_ciclo = curva_por_edad.loc[mask, "edad"].to_numpy(dtype=int)
        valores_ciclo = curva_por_edad.loc[mask, "fm_suave"].to_numpy(dtype=float)
        curva_por_edad.loc[mask, "fm_suave"] = _keep_strongest_consecutive_run(edades_ciclo, valores_ciclo)

    curva_por_edad = _force_cycle_1_valley_by_peak(curva_por_edad, peak_cycle_1_age, valley_weeks_after_peak)

    curva_por_edad["fm_suave"] = rescale_to_total(curva_por_edad["fm_suave"].to_numpy(), temp["f_m"].sum())
    return _sort_report_rows(
        temp.merge(curva_por_edad[["edad", "fm_suave"]], on="edad", how="left"),
        DETAIL_SORT_COLUMNS,
    )


def _calculate_peak_age(grupo: pd.DataFrame) -> float:
    grupo = grupo.sort_values("edad").reset_index(drop=True)
    if grupo.empty:
        return np.nan

    ciclo = pd.to_numeric(grupo["ciclo"], errors="coerce").dropna()
    if ciclo.empty:
        return np.nan

    window_size = min(_window_size_for_ciclo(int(ciclo.iloc[0])), len(grupo))
    if window_size <= 0:
        return np.nan

    rolling_sum = grupo["f_m"].rolling(window=window_size).sum()
    idx_max_window = rolling_sum.idxmax()
    if pd.isna(idx_max_window):
        return np.nan
    return float(grupo.loc[int(idx_max_window), "edad"])


def _tukey_bounds(values: pd.Series) -> tuple[float, float]:
    q1 = values.quantile(0.25)
    q3 = values.quantile(0.75)
    iqr = q3 - q1
    return float(q1 - 1.5 * iqr), float(q3 + 1.5 * iqr)


def _annotate_cycle_peaks(df: pd.DataFrame, group_columns: list[str]) -> pd.DataFrame:
    resultados: list[pd.DataFrame] = []

    for _, grupo in df.groupby(group_columns, sort=False):
        grupo_out = grupo.sort_values("edad").copy()
        grupo_out["pico"] = _calculate_peak_age(grupo_out)
        resultados.append(grupo_out)

    if not resultados:
        raise RuntimeError("No se pudieron calcular picos por ciclo.")

    df_out = pd.concat(resultados, ignore_index=True)
    df_out["pico"] = pd.to_numeric(df_out["pico"], errors="coerce").round().astype("Int64")
    return df_out


def _apply_curve_filter(df: pd.DataFrame, group_columns: list[str], variety_column: str) -> pd.DataFrame:
    if df.empty:
        return df.assign(**{FILTER_COLUMN: pd.Series(dtype="int64")})

    curve_stats = (
        df.groupby(group_columns, dropna=False, as_index=False)
        .agg(puntos=("edad", "size"), suma_fm=("f_m", "sum"))
    )

    thresholds = (
        curve_stats.groupby([variety_column, "ciclo"], dropna=False)
        .agg(
            q1=("suma_fm", lambda series: series.quantile(0.25)),
            q3=("suma_fm", lambda series: series.quantile(0.75)),
        )
        .reset_index()
    )
    thresholds["lower_bound"] = thresholds["q1"] - 1.5 * (thresholds["q3"] - thresholds["q1"])
    thresholds["upper_bound"] = thresholds["q3"] + 1.5 * (thresholds["q3"] - thresholds["q1"])

    curve_stats = curve_stats.merge(thresholds, on=[variety_column, "ciclo"], how="left")
    puntos_ok = (
        ((curve_stats["ciclo"] == 1) & (curve_stats["puntos"] > MIN_POINTS_CYCLE_1))
        | ((curve_stats["ciclo"] == 2) & (curve_stats["puntos"] > MIN_POINTS_CYCLE_2))
    )
    tukey_ok = curve_stats["suma_fm"].between(curve_stats["lower_bound"], curve_stats["upper_bound"], inclusive="both")
    curve_stats[FILTER_COLUMN] = np.where(puntos_ok & tukey_ok, 1, 0)

    return df.merge(curve_stats[group_columns + [FILTER_COLUMN]], on=group_columns, how="left")


def _load_source(fecha_inicio: pd.Timestamp, fecha_fin: pd.Timestamp) -> pd.DataFrame:
    source_path = Path(normalize_path(settings.TABLA_CURVAS_CLAVEL_OUTPUT_CSV))
    if not source_path.exists():
        raise FileNotFoundError(f"No existe el insumo de curvas: {source_path}")

    columnas = [
        "finca",
        "bloque",
        "cosecha",
        "nvariedad",
        "edad",
        "matas",
        "corte",
        "lunes",
    ]
    df = pd.read_csv(
        source_path,
        usecols=columnas,
        converters={"finca": str, "cosecha": str, "nvariedad": str},
        na_values=["(en blanco)"],
    )
    if df.empty:
        raise RuntimeError("El archivo tabla_curvas_clavel.csv no contiene datos.")

    df = df.rename(columns={"lunes": "fecha"})
    df["cosecha"] = df["cosecha"].fillna("")
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["edad"] = pd.to_numeric(df["edad"], errors="coerce")
    df["matas"] = pd.to_numeric(df["matas"], errors="coerce")
    df["corte"] = pd.to_numeric(df["corte"], errors="coerce")

    df = df.dropna(subset=["fecha", "edad", "matas", "corte"])
    df = df[(df["fecha"] >= fecha_inicio) & (df["fecha"] <= fecha_fin)].copy()
    if df.empty:
        raise RuntimeError(
            f"No hay datos de curvas entre {fecha_inicio.strftime('%Y-%m-%d')} y {fecha_fin.strftime('%Y-%m-%d')} para procesar."
        )
    return df


def _load_discarded_curves() -> pd.DataFrame:
    rows = execute_query(
        "SELECT finca, bloque, nvariedad, cosecha FROM ld_descarta_curva"
    ) or []
    df = pd.DataFrame(rows, columns=["finca", "bloque", "nvariedad", "cosecha"])
    if df.empty:
        return df

    df["finca"] = df["finca"].astype(str).str.strip()
    df["nvariedad"] = df["nvariedad"].astype(str).str.strip()
    df["cosecha"] = df["cosecha"].astype(str).str.strip()
    df["bloque"] = pd.to_numeric(df["bloque"], errors="coerce")
    return df.dropna(subset=["bloque"])


def _exclude_discarded_curves(df_raw: pd.DataFrame) -> pd.DataFrame:
    descartadas = _load_discarded_curves()
    if descartadas.empty:
        return df_raw

    df = df_raw.copy()
    df["bloque"] = pd.to_numeric(df["bloque"], errors="coerce")
    marcador = descartadas.assign(_descartada=True)
    filtrado = df.merge(marcador, on=["finca", "bloque", "nvariedad", "cosecha"], how="left")
    filtrado = filtrado[filtrado["_descartada"].isna()].drop(columns=["_descartada"])
    if filtrado.empty:
        raise RuntimeError("Todas las curvas fueron excluidas por ld_descarta_curva.")
    return filtrado.reset_index(drop=True)


def _build_base(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()
    df["edad"] = df["edad"].astype(int)
    df = df[df["edad"] <= MAX_PRODUCTION_AGE].copy()
    if df.empty:
        raise RuntimeError(f"No quedaron registros con edad <= {MAX_PRODUCTION_AGE}.")

    df["ciclo"] = df["edad"].apply(_asignar_ciclo)
    df["f_m"] = np.where(df["matas"] > 0, df["corte"] / df["matas"], np.nan)
    df = df.dropna(subset=["f_m"]).copy()
    if df.empty:
        raise RuntimeError("No se generó información base para el pipeline de curvas.")

    return df.groupby(["finca", "bloque", "nvariedad", "cosecha", "edad", "ciclo"], as_index=False)["f_m"].mean()


def _resolve_smoothing_params(params: dict | None) -> dict[str, int]:
    raw_params = params or {}
    resolved: dict[str, int] = {}

    for key, default_value in DEFAULT_SMOOTHING_PARAMS.items():
        value = raw_params.get(key, default_value)
        try:
            resolved[key] = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Parametro invalido '{key}': {value}") from exc

    resolved["sem_valle"] = max(0, resolved["sem_valle"])
    resolved["peak_window_weeks"] = max(1, resolved["peak_window_weeks"])
    resolved["smooth_window_length"] = max(3, resolved["smooth_window_length"])
    resolved["smooth_polyorder"] = max(0, resolved["smooth_polyorder"])
    resolved["force_valley_weeks_after_peak"] = max(0, resolved["force_valley_weeks_after_peak"])
    return resolved


def _smooth_curves(df: pd.DataFrame, smoothing_params: dict[str, int]) -> pd.DataFrame:
    resultados: list[pd.DataFrame] = []
    grupos = df[["finca", "bloque", "nvariedad", "cosecha", "ciclo"]].drop_duplicates()

    for _, row in grupos.iterrows():
        finca = row["finca"]
        bloque = row["bloque"]
        variedad = row["nvariedad"]
        cosecha = row["cosecha"]
        ciclo = row["ciclo"]
        temp = df[
            (df["finca"] == finca)
            & (df["bloque"] == bloque)
            & (df["nvariedad"] == variedad)
            & (df["cosecha"] == cosecha)
            & (df["ciclo"] == ciclo)
        ].copy()
        temp = temp.sort_values("edad").reset_index(drop=True)
        peak_cycle_1_age = _calculate_peak_age(temp[temp["ciclo"] == 1].copy())
        peak_cycle_1_age_int = None if pd.isna(peak_cycle_1_age) else int(round(float(peak_cycle_1_age)))

        try:
            curva = np.array(curve_ini(temp))
            _, _, suavizada = datos_curva(
                curva,
                sem_valle=smoothing_params["sem_valle"],
                peak_window_weeks=smoothing_params["peak_window_weeks"],
                smooth_window_length=smoothing_params["smooth_window_length"],
                smooth_polyorder=smoothing_params["smooth_polyorder"],
            )
            resultados.append(
                _enforce_smoothed_curve_rules(
                    temp,
                    suavizada,
                    peak_cycle_1_age=peak_cycle_1_age_int,
                    valley_weeks_after_peak=smoothing_params["force_valley_weeks_after_peak"],
                )
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"No se pudo suavizar la curva {finca}-{bloque}-{variedad}-{cosecha}-{ciclo}: {exc}") from exc

    if not resultados:
        raise RuntimeError("No se generaron curvas suavizadas.")

    return _sort_report_rows(pd.concat(resultados, ignore_index=True), DETAIL_SORT_COLUMNS)


def _build_summary(df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        df.groupby(["finca", "nvariedad", "ciclo", "edad"], as_index=False)["f_m"]
        .mean()
    )
    grouped_all_farms = (
        df.groupby(["nvariedad", "ciclo", "edad"], as_index=False)["f_m"]
        .mean()
    )
    grouped_all_farms["finca"] = ALL_FARMS_CODE
    grouped_all_farms = grouped_all_farms[["finca", "nvariedad", "ciclo", "edad", "f_m"]]
    # El pico operativo se sigue calculando sobre f_m, no sobre fm_suave.
    grouped = _annotate_cycle_peaks(grouped, ["finca", "nvariedad", "ciclo"])
    grouped_all_farms = _annotate_cycle_peaks(grouped_all_farms, ["finca", "nvariedad", "ciclo"])
    grouped = pd.concat([grouped, grouped_all_farms], ignore_index=True)

    summary = (
        grouped.groupby(["finca", "nvariedad", "ciclo"], as_index=False)
        .agg({"f_m": "sum", "pico": "first"})
        .sort_values(["finca", "nvariedad", "ciclo"])
        .reset_index(drop=True)
    )
    summary["pico"] = pd.to_numeric(summary["pico"], errors="coerce").astype("Int64")
    summary[FILTER_COLUMN] = 1
    return _sort_report_rows(summary, SUMMARY_SORT_COLUMNS)


def _build_filtered_curve_summary(df: pd.DataFrame, smoothing_params: dict[str, int]) -> pd.DataFrame:
    filtered = df[df[FILTER_COLUMN] == 1].copy()
    if filtered.empty:
        raise RuntimeError("No se encontraron curvas con filtro=1 para exportar la salida filtrada.")

    grouped = filtered.groupby(["finca", "nvariedad", "edad"], as_index=False)["f_m"].mean()
    grouped["edad"] = grouped["edad"].astype(int)

    resultados: list[pd.DataFrame] = []
    for _, grupo in grouped.groupby(["finca", "nvariedad"], sort=False):
        grupo = grupo.sort_values("edad").copy()
        curva = grupo.set_index("edad")["f_m"].reindex(CURVE_SUMMARY_AGES, fill_value=0.0).to_numpy(dtype=float)
        _, _, suavizada = datos_curva(
            curva,
            sem_valle=smoothing_params["sem_valle"],
            peak_window_weeks=smoothing_params["peak_window_weeks"],
            smooth_window_length=smoothing_params["smooth_window_length"],
            smooth_polyorder=smoothing_params["smooth_polyorder"],
        )
        salida = pd.DataFrame(
            {
                "finca": grupo["finca"].iloc[0],
                "nvariedad": grupo["nvariedad"].iloc[0],
                "edad": CURVE_SUMMARY_AGES,
                "ciclo": pd.Series(CURVE_SUMMARY_AGES).apply(_asignar_ciclo),
                "f_m": curva,
                "fm_suave": suavizada,
            }
        )
        resultados.append(salida)

    if not resultados:
        raise RuntimeError("No se pudo construir la salida filtrada de curvas.")

    return _sort_report_rows(pd.concat(resultados, ignore_index=True), ["finca", "nvariedad", "edad"])


def generate_production_pipeline(params: dict | None = None) -> str:
    smoothing_params = _resolve_smoothing_params(params)
    fecha_inicio, fecha_fin = resolve_date_range_params(params)
    df_raw = _load_source(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
    df_raw = _exclude_discarded_curves(df_raw)
    base = _build_base(df_raw)
    final = _sort_report_rows(
        _annotate_cycle_peaks(
            _smooth_curves(base, smoothing_params),
            ["finca", "bloque", "nvariedad", "cosecha", "ciclo"],
        ),
        DETAIL_SORT_COLUMNS,
    )
    final = _apply_curve_filter(final, ["finca", "bloque", "nvariedad", "cosecha", "ciclo"], "nvariedad")
    resumen = _build_summary(final[final[FILTER_COLUMN] == 1].copy())
    curvas_filtradas = _build_filtered_curve_summary(final, smoothing_params)

    detail_output = Path(normalize_path(settings.CURVAS_PRODUCCION_OUTPUT_PATH))
    summary_output = Path(normalize_path(settings.CURVAS_PRODUCCION_RESUMEN_OUTPUT_PATH))
    filtered_output = Path(normalize_path(settings.CURVAS_PRODUCCION_FILTRADA_OUTPUT_PATH))
    detail_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    filtered_output.parent.mkdir(parents=True, exist_ok=True)

    final.to_excel(detail_output, index=False)
    resumen.to_csv(summary_output, index=False, encoding="utf-8-sig")
    curvas_filtradas.to_csv(filtered_output, index=False, encoding="utf-8-sig")

    return f"xlsx:{detail_output} | csv:{summary_output} | csv:{filtered_output}"