"""Genera un resumen de curvas Tika por programa y variedad."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import unicodedata

import numpy as np
import pandas as pd

from app.services.dbf_reader import normalize_path
from app.services.etl_helpers import dataframe_to_sql, execute_query, validate_columns


def _normalize_column_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(name))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return normalized.strip().lower().replace(" ", "_")


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
    if len(grupo) < 4:
        grupo["pico"] = np.nan
        grupo["suma_pico"] = np.nan
        grupo["puntos_pico"] = np.nan
        grupo["termina_curva"] = np.nan
        grupo["puntos"] = len(grupo)
        return grupo

    rolling_sum = grupo["fm"].rolling(window=4).sum()
    idx_max_window = rolling_sum.idxmax()
    max_sum = rolling_sum.max()
    ventana = 4

    if max_sum < 3.2 and len(grupo) >= 5:
        rolling_sum = grupo["fm"].rolling(window=5).sum()
        idx_max_window = rolling_sum.idxmax()
        max_sum = rolling_sum.max()
        ventana = 5

    grupo["pico"] = grupo.loc[idx_max_window, "edad"]
    grupo["suma_pico"] = max_sum
    grupo["puntos_pico"] = ventana
    mask = grupo["fm"] > 0
    grupo["termina_curva"] = grupo.loc[mask, "edad"].iloc[-1] if mask.any() else np.nan
    grupo["puntos"] = len(grupo)
    return grupo


def _resolve_curve_sources(params: dict[str, Any] | None) -> list[tuple[str, int]]:
    raw_paths = list((params or {}).get("curve_paths") or [])
    raw_years = list((params or {}).get("curve_years") or [])
    if not raw_paths or not raw_years:
        raise ValueError("Debes enviar 'curve_paths' y 'curve_years'.")
    if len(raw_paths) != len(raw_years):
        raise ValueError("'curve_paths' y 'curve_years' deben tener la misma cantidad de elementos.")

    sources: list[tuple[str, int]] = []
    for path_value, year_value in zip(raw_paths, raw_years, strict=True):
        path = str(path_value).strip()
        if not path:
            continue
        sources.append((path, int(year_value)))

    if not sources:
        raise ValueError("No se encontraron curvas válidas para procesar.")
    return sources


def _build_curvas_resumen_todas() -> pd.DataFrame:
    rows_curvas = execute_query(
        """
        SELECT
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
        columns=["finca", "flor", "bloque", "variedad", "cosecha", "edad", "fm", "descarta_curva"],
    )
    if df_curvas.empty:
        raise RuntimeError("No hay datos en ld_curvas_clavel para construir curvas_resumen_todas.csv.")

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
    df_curvas["flor"] = df_curvas["flor"].astype(str).str.strip()
    df_curvas["variedad"] = df_curvas["variedad"].astype(str).str.strip().str.replace(" ", "_", regex=False)
    df_curvas["cosecha"] = df_curvas["cosecha"].astype(str).str.strip()
    df_curvas = df_curvas.dropna(subset=["edad", "fm", "finca", "flor", "bloque", "variedad", "cosecha"])
    df_curvas = df_curvas.query("edad >= 17 and edad <= 70").copy()
    df_curvas = df_curvas[df_curvas["flor"].isin(["CLA", "CM0"]) & (df_curvas["cosecha"] != "VITRI")].copy()

    df_curvas["ciclo"] = np.select(
        [df_curvas["edad"] <= 35, df_curvas["edad"] <= 70],
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
    df_resultado2_clean = df_resultado2.dropna().copy()

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

    frames = [_procesar_curvas(path_csv=path_csv, anio=anio) for path_csv, anio in sources]
    df_resultado = pd.concat(frames, ignore_index=True)
    df_resultado = df_resultado.query("edad >= 17 and edad <= 70").copy()

    df_resultado["ciclo"] = np.select(
        [df_resultado["edad"] <= 35, df_resultado["edad"] <= 70],
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
        raise RuntimeError("No hay datos válidos para resumir curvas en el rango de edad 17-70.")

    df_resultado = pd.concat(processed_groups, ignore_index=True)

    resumen = (
        df_resultado
        .groupby(["prg", "variedad", "ciclo"], dropna=False)["fm"]
        .sum()
        .unstack(fill_value=0)
        .reindex(columns=[1, 2], fill_value=0)
        .rename(columns={1: "suma_ciclo1", 2: "suma_ciclo2"})
        .reset_index()
    )
    resumen["suma_total"] = resumen[["suma_ciclo1", "suma_ciclo2"]].sum(axis=1)

    df_ppico = (
        df_resultado.query("ciclo == 1")
        .groupby(["prg", "variedad"], dropna=False)
        .agg({"pico": "first", "suma_pico": "first"})
        .reset_index()
    )

    df_export = (
        df_resultado
        .drop(columns=["pico", "suma_pico"], errors="ignore")
        .merge(resumen, on=["prg", "variedad"], how="left")
        .merge(df_ppico, on=["prg", "variedad"], how="left")
    )

    dataframe_to_sql(df_resultado, "resumen_curvas", if_exists="replace")

    output_path = Path(normalize_path(r"//172.10.18.2/Usuarios/Outputs/curvas_resumen.csv"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_export.to_csv(output_path, index=False, encoding="utf-8-sig")

    df_export3 = _build_curvas_resumen_todas()
    output_todas_path = Path(normalize_path(r"//172.10.18.2/Usuarios/Outputs/curvas_resumen_todas.csv"))
    output_todas_path.parent.mkdir(parents=True, exist_ok=True)
    df_export3.to_csv(output_todas_path, index=False, encoding="utf-8-sig")

    return f"mysql:informes.resumen_curvas | csv:{output_path} | csv:{output_todas_path}"
