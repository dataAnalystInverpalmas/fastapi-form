"""Genera un resumen de curvas Tika por programa y variedad."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import unicodedata

import numpy as np
import pandas as pd

from app.services.utils.dbf_reader import normalize_path
from app.services.etl.helpers import dataframe_to_sql, execute_query, validate_columns


MIN_POINTS_CYCLE_1 = 8
MIN_POINTS_CYCLE_2 = 14
FILTER_COLUMN = "filtro"
SELECTED_FILTER_VALUE = 2
DEFAULT_EXPORT_FILTER_MIN = 2


def _tukey_bounds(values: pd.Series) -> tuple[float, float]:
    q1 = values.quantile(0.25)
    q3 = values.quantile(0.75)
    iqr = q3 - q1
    return float(q1 - 1.5 * iqr), float(q3 + 1.5 * iqr)


def _normalize_column_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(name))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return normalized.strip().lower().replace(" ", "_")


def _mode_peak_value(values: pd.Series) -> float:
    valid_values = pd.to_numeric(values, errors="coerce").dropna()
    if valid_values.empty:
        return np.nan

    mode_values = valid_values.mode()
    if mode_values.empty:
        return np.nan

    return float(mode_values.min())


def _date_series_to_yyww(values: pd.Series) -> pd.Series:
    fechas = pd.to_datetime(values, errors="coerce")
    iso = fechas.dt.isocalendar()
    return ((iso.year % 100) * 100 + iso.week).astype("Int64")


def _resolve_export_filter_min(params: dict[str, Any] | None) -> int:
    raw_value = (params or {}).get("final_filter_value", DEFAULT_EXPORT_FILTER_MIN)
    try:
        filter_min = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("'final_filter_value' debe ser un entero entre 0 y 2.") from exc

    if filter_min < 0 or filter_min > SELECTED_FILTER_VALUE:
        raise ValueError("'final_filter_value' debe estar entre 0 y 2.")
    return filter_min


def _procesar_curvas(path_csv: str, anio: int) -> pd.DataFrame:
    csv_path = Path(normalize_path(path_csv))
    if not csv_path.exists():
        raise FileNotFoundError(f"No existe el archivo de curvas: {csv_path}")

    df = pd.read_csv(csv_path, thousands=",", low_memory=False)
    colmap = {_normalize_column_name(col): col for col in df.columns}
    required = {"variedad", "numero_de_semana", "produccion"}
    if not required.issubset(colmap.keys()):
        # Reusa el helper para devolver un error consistente con el resto del ETL.
        renamed = df.rename(columns={
            colmap.get("variedad", "variedad"): "variedad",
            colmap.get("numero_de_semana", "numero_de_semana"): "numero_de_semana",
            colmap.get("produccion", "produccion"): "produccion",
        })
        validate_columns(renamed, required, csv_path.name)

    df = df.rename(columns={
        colmap["variedad"]: "variedad",
        colmap["numero_de_semana"]: "edad",
        colmap["produccion"]: "fm",
    })
    df["variedad"] = df["variedad"].astype(str).str.strip().str.replace(" ", "_", regex=False)
    df["edad"] = pd.to_numeric(df["edad"], errors="coerce")
    df["fm"] = pd.to_numeric(df["fm"], errors="coerce").fillna(0)
    df["prg"] = int(anio)
    df = df[["variedad", "edad", "fm", "prg"]].dropna(subset=["edad"]).sort_values(["variedad", "edad"])
    return df


def _calcular_usemana(grupo: pd.DataFrame) -> pd.DataFrame:
    grupo = grupo.reset_index(drop=True)
    ciclo_value = pd.to_numeric(grupo.get("ciclo"), errors="coerce").dropna()
    window_size = 4
    if not ciclo_value.empty:
        ciclo = int(ciclo_value.iloc[0])
        if ciclo == 2:
            window_size = 10

    if len(grupo) < window_size:
        grupo["pico"] = np.nan
        grupo["suma_pico"] = np.nan
        grupo["puntos_pico"] = np.nan
        grupo["termina_curva"] = np.nan
        grupo["puntos"] = len(grupo)
        return grupo

    rolling_sum = grupo["fm"].rolling(window=window_size, min_periods=window_size).sum()
    idx_max_window = rolling_sum.idxmax()
    max_sum = rolling_sum.max()

    grupo["pico"] = grupo.loc[idx_max_window, "edad"]
    grupo["suma_pico"] = max_sum
    grupo["puntos_pico"] = window_size
    mask = grupo["fm"] > 0
    grupo["termina_curva"] = grupo.loc[mask, "edad"].iloc[-1] if mask.any() else np.nan
    grupo["puntos"] = len(grupo)
    return grupo


def _apply_curve_filter(
    df: pd.DataFrame,
    group_columns: list[str],
    variety_column: str,
    cycle_column: str = "ciclo",
) -> pd.DataFrame:
    if df.empty:
        return df.assign(**{FILTER_COLUMN: pd.Series(dtype="int64")})

    curve_stats = (
        df.groupby(group_columns, dropna=False, as_index=False)
        .agg(puntos=("edad", "size"), suma_fm=("fm", "sum"))
    )

    thresholds = (
        curve_stats.groupby([variety_column, cycle_column], dropna=False)
        .agg(
            q1=("suma_fm", lambda series: series.quantile(0.25)),
            q3=("suma_fm", lambda series: series.quantile(0.75)),
        )
        .reset_index()
    )
    thresholds["lower_bound"] = thresholds["q1"] - 1.5 * (thresholds["q3"] - thresholds["q1"])
    thresholds["upper_bound"] = thresholds["q3"] + 1.5 * (thresholds["q3"] - thresholds["q1"])

    curve_stats = curve_stats.merge(thresholds, on=[variety_column, cycle_column], how="left")

    puntos_ok = (
        ((curve_stats[cycle_column] == 1) & (curve_stats["puntos"] >= MIN_POINTS_CYCLE_1))
        | ((curve_stats[cycle_column] == 2) & (curve_stats["puntos"] >= MIN_POINTS_CYCLE_2))
    )
    tukey_ok = curve_stats["suma_fm"].between(curve_stats["lower_bound"], curve_stats["upper_bound"], inclusive="both")
    curve_stats[FILTER_COLUMN] = np.where(puntos_ok & tukey_ok, 1, 0)

    if "pico" in df.columns:
        peak_stats = (
            df.groupby(group_columns, dropna=False, as_index=False)
            .agg(pico=("pico", "first"))
        )
        curve_stats = curve_stats.merge(peak_stats, on=group_columns, how="left")

        peak_modes = (
            curve_stats[curve_stats[FILTER_COLUMN] == 1]
            .groupby([variety_column, cycle_column], dropna=False, as_index=False)
            .agg(pico_moda=("pico", _mode_peak_value))
        )
        curve_stats = curve_stats.merge(peak_modes, on=[variety_column, cycle_column], how="left")

        near_peak_mode = curve_stats["pico"].between(
            curve_stats["pico_moda"] - 2,
            curve_stats["pico_moda"] + 2,
            inclusive="both",
        )
        curve_stats[FILTER_COLUMN] = np.where(
            (curve_stats[FILTER_COLUMN] == 1) & near_peak_mode,
            SELECTED_FILTER_VALUE,
            curve_stats[FILTER_COLUMN],
        )

    return df.merge(curve_stats[group_columns + [FILTER_COLUMN]], on=group_columns, how="left")


def _split_param_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [item for item in value if item is not None]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if "\n" in text or "\r" in text:
            return [item.strip() for item in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if item.strip()]
        if ";" in text:
            return [item.strip() for item in text.split(";") if item.strip()]
        if "," in text:
            return [item.strip() for item in text.split(",") if item.strip()]
        return [text]
    return [value]


def _resolve_curve_sources(params: dict[str, Any] | None) -> list[tuple[str, int]]:
    raw_paths = _split_param_list((params or {}).get("curve_paths"))
    raw_years = _split_param_list((params or {}).get("curve_years"))
    if not raw_paths or not raw_years:
        raise ValueError("Debes enviar 'curve_paths' y 'curve_years'.")
    if len(raw_paths) != len(raw_years):
        raise ValueError("'curve_paths' y 'curve_years' deben tener la misma cantidad de elementos.")

    sources: list[tuple[str, int]] = []
    for path_value, year_value in zip(raw_paths, raw_years, strict=True):
        path = str(path_value).strip()
        if not path:
            continue
        try:
            year = int(year_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Año inválido para la curva '{path}': {year_value!r}.") from exc
        sources.append((path, year))

    if not sources:
        raise ValueError("No se encontraron curvas válidas para procesar.")
    return sources


def _build_curvas_resumen_todas(export_filter_min: int = DEFAULT_EXPORT_FILTER_MIN) -> pd.DataFrame:
    rows_curvas = execute_query(
        """
        SELECT
            c.lunes AS fecha_curva,
            c.finca,
            c.cflor AS flor,
            c.bloque,
            REPLACE(c.nvariedad, ' ', '_') AS variedad,
            c.cosecha,
            c.edad,
            c.f_m AS fm,
            IF(d.finca IS NULL, 0, 1) AS descarta_curva
        FROM ld_curvas_clavel AS c
        LEFT JOIN ld_descarta_curva AS d
            ON d.finca = c.finca
            AND d.variedad = c.variedad
            AND d.cosecha = c.cosecha
            AND d.bloque = c.bloque
        """
    ) or []
    df_curvas = pd.DataFrame(
        rows_curvas,
        columns=["fecha_curva", "finca", "flor", "bloque", "variedad", "cosecha", "edad", "fm", "descarta_curva"],
    )
    if df_curvas.empty:
        return pd.DataFrame(
            columns=[
                "fecha_curva",
                "finca",
                "flor",
                "bloque",
                "variedad",
                "cosecha",
                "edad",
                "fm",
                "descarta_curva",
                "ciclo",
                "pico",
                "suma_pico",
                "puntos",
                "puntos_ppico",
                "ncosecha",
                "yyww",
                "meta",
                "dif",
            ]
        )

    rows_metas = execute_query(
        """
        SELECT
            finca,
            bloque,
            REPLACE(nvariedad, ' ', '_') AS variedad,
            cosecha,
            cantidad AS meta
        FROM ld_metas
        """
    ) or []
    df_metas = pd.DataFrame(rows_metas, columns=["finca", "bloque", "variedad", "cosecha", "meta"])
    if not df_metas.empty:
        df_metas = df_metas.drop_duplicates(subset=["finca", "bloque", "variedad", "cosecha"], keep="last")

    rows_cosechas = execute_query(
        """
        SELECT
            cod_temporada AS cosecha,
            ncosecha
        FROM seasons
        """
    ) or []
    df_cosechas = pd.DataFrame(rows_cosechas, columns=["cosecha", "ncosecha"])

    df_curvas["edad"] = pd.to_numeric(df_curvas["edad"], errors="coerce")
    df_curvas["fm"] = pd.to_numeric(df_curvas["fm"], errors="coerce")
    df_curvas["fecha_curva"] = pd.to_datetime(df_curvas["fecha_curva"], errors="coerce")
    df_curvas["flor"] = df_curvas["flor"].astype(str).str.strip()
    df_curvas["variedad"] = df_curvas["variedad"].astype(str).str.strip().str.replace(" ", "_", regex=False)
    df_curvas["cosecha"] = df_curvas["cosecha"].astype(str).str.strip()
    df_curvas = df_curvas.dropna(subset=["edad", "fm", "finca", "flor", "bloque", "variedad", "cosecha"])
    df_curvas = df_curvas.query("edad >= 17 and edad <= 70").copy()
    df_curvas = df_curvas[df_curvas["flor"].isin(["CLA", "CM0"])].copy() #& (df_curvas["cosecha"] != "VITRI")

    df_curvas["ciclo"] = np.select(
        [df_curvas["edad"] <= 35, df_curvas["edad"] <= 68],
        [1, 2],
        default=3,
    )

    grouped_rows: list[pd.DataFrame] = []
    for key, grupo in df_curvas.groupby(["finca", "flor", "bloque", "variedad", "ciclo", "cosecha"], sort=False):
        finca, flor, bloque, variedad, ciclo, cosecha = key
        grupo_out = _calcular_usemana(grupo.copy())
        grupo_out["finca"] = finca
        grupo_out["flor"] = flor
        grupo_out["bloque"] = bloque
        grupo_out["variedad"] = variedad
        grupo_out["ciclo"] = ciclo
        grupo_out["cosecha"] = cosecha
        grouped_rows.append(grupo_out)

    if not grouped_rows:
        raise RuntimeError("No hay datos válidos para exportar curvas_resumen_todas.csv.")

    df_resultado2 = pd.concat(grouped_rows, ignore_index=True)
    df_resultado2 = _apply_curve_filter(
        df_resultado2,
        ["finca", "bloque", "variedad", "cosecha", "ciclo"],
        "variedad",
    )
    df_resultado2_clean = df_resultado2.dropna().copy()
    df_resultado2_clean = df_resultado2_clean[df_resultado2_clean[FILTER_COLUMN] >= export_filter_min].copy()
    if df_resultado2_clean.empty:
        raise RuntimeError(
            "Ninguna curva de ld_curvas_clavel cumplió el filtro para exportar curvas_resumen_todas.csv "
            f"(final_filter_value={export_filter_min})."
        )

    resumen2 = (
        df_resultado2_clean
        .groupby(["finca", "bloque", "variedad", "cosecha", "ciclo"], dropna=False)["fm"]
        .sum()
        .unstack(fill_value=0)
        .reindex(columns=[1, 2], fill_value=0)
        .rename(columns={1: "suma_ciclo1", 2: "suma_ciclo2"})
        .reset_index()
    )
    resumen2["suma_total"] = resumen2[["suma_ciclo1", "suma_ciclo2"]].sum(axis=1)

    df_ppico2 = (
        df_resultado2_clean.query("ciclo == 1")
        .groupby(["finca", "bloque", "variedad", "cosecha"], dropna=False)
        .agg({"pico": "first", "suma_pico": "first", "puntos": "first"})
        .reset_index()
    )

    df_export2 = (
        df_resultado2_clean
        .drop(columns=["pico", "suma_pico"], errors="ignore")
        .merge(resumen2, on=["finca", "bloque", "variedad", "cosecha"], how="left")
        .merge(df_ppico2, on=["finca", "bloque", "variedad", "cosecha"], how="left", suffixes=("_base", "_ppico"))
    )

    # Mantiene una sola columna de puntos de pico con nombre estable.
    if "puntos_base" in df_export2.columns:
        df_export2 = df_export2.drop(columns=["puntos_base"])
    if "puntos_ppico" not in df_export2.columns and "puntos" in df_export2.columns:
        df_export2 = df_export2.rename(columns={"puntos": "puntos_ppico"})

    if not df_cosechas.empty:
        df_export3 = pd.merge(df_export2, df_cosechas, on="cosecha", how="left")
    else:
        df_export3 = df_export2.copy()

    df_export3["yyww"] = _date_series_to_yyww(df_export3["fecha_curva"])

    if not df_metas.empty and {"finca", "bloque", "variedad", "cosecha", "suma_ciclo1"}.issubset(set(resumen2.columns)):
        df_meta_real = pd.merge(
            resumen2,
            df_metas,
            on=["finca", "bloque", "variedad", "cosecha"],
            how="inner",
        )
        if not df_meta_real.empty:
            df_meta_real["dif"] = np.round(df_meta_real["suma_ciclo1"] - pd.to_numeric(df_meta_real["meta"], errors="coerce"), 2)

    return df_export3


def generate_resumir_curvas_usadas(params: dict[str, Any] | None = None) -> str:
    sources = _resolve_curve_sources(params)
    export_filter_min = _resolve_export_filter_min(params)

    frames = [_procesar_curvas(path_csv=path_csv, anio=anio) for path_csv, anio in sources]
    df_resultado = pd.concat(frames, ignore_index=True)
    df_resultado = df_resultado.query("edad >= 17 and edad <= 68").copy()

    df_resultado["ciclo"] = np.select(
        [df_resultado["edad"] <= 35, df_resultado["edad"] <= 68],
        [1, 2],
        default=3,
    )

    processed_groups: list[pd.DataFrame] = []
    for (prg, variedad, ciclo), grupo in df_resultado.groupby(["prg", "variedad", "ciclo"], sort=False):
        grupo_out = _calcular_usemana(grupo.copy())
        grupo_out["prg"] = prg
        grupo_out["variedad"] = variedad
        grupo_out["ciclo"] = ciclo
        processed_groups.append(grupo_out)

    if not processed_groups:
        raise RuntimeError("No hay datos válidos para resumir curvas en el rango de edad 17-68.")

    df_resultado = pd.concat(processed_groups, ignore_index=True)
    df_resultado = _apply_curve_filter(df_resultado, ["prg", "variedad", "ciclo"], "variedad")
    df_resultado_filtrado = df_resultado[df_resultado[FILTER_COLUMN] >= export_filter_min].copy()
    if df_resultado_filtrado.empty:
        raise RuntimeError(
            "Ninguna curva cumplió el filtro para exportar curvas_resumen.csv "
            f"(final_filter_value={export_filter_min})."
        )

    resumen = (
        df_resultado_filtrado
        .groupby(["prg", "variedad", "ciclo"], dropna=False)["fm"]
        .sum()
        .unstack(fill_value=0)
        .reindex(columns=[1, 2], fill_value=0)
        .rename(columns={1: "suma_ciclo1", 2: "suma_ciclo2"})
        .reset_index()
    )
    resumen["suma_total"] = resumen[["suma_ciclo1", "suma_ciclo2"]].sum(axis=1)

    df_ppico = (
        df_resultado_filtrado.query("ciclo == 1")
        .groupby(["prg", "variedad"], dropna=False)
        .agg({"pico": "first", "suma_pico": "first"})
        .reset_index()
    )

    df_export = (
        df_resultado_filtrado
        .drop(columns=["pico", "suma_pico"], errors="ignore")
        .merge(resumen, on=["prg", "variedad"], how="left")
        .merge(df_ppico, on=["prg", "variedad"], how="left")
    )

    dataframe_to_sql(df_resultado, "resumen_curvas", if_exists="replace")

    output_path = Path(normalize_path(r"//172.10.18.2/Usuarios/Outputs/curvas_resumen.csv"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_export.to_csv(output_path, index=False, encoding="utf-8-sig")

    df_export3 = _build_curvas_resumen_todas(export_filter_min=export_filter_min)
    output_todas_path = Path(normalize_path(r"//172.10.18.2/Usuarios/Outputs/curvas_resumen_todas.csv"))
    output_todas_path.parent.mkdir(parents=True, exist_ok=True)
    df_export3.to_csv(output_todas_path, index=False, encoding="utf-8-sig")

    return f"mysql:informes.resumen_curvas | csv:{output_path} | csv:{output_todas_path}"
