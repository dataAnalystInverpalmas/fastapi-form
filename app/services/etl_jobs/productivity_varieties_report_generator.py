from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.settings import settings
from app.services.dbf_reader import normalize_path
from app.services.etl_helpers import execute_query, normalize_finca_series, validate_columns


PRODUCTIVITIES_BASE_QUERY = """
    SELECT
        p.producto AS flor,
        c.orden AS orden_color,
        c.nombre AS color,
        p.variedad,
        IF(p.finca = 'INVERPALMAS', '001', '002') AS finca
    FROM plane AS p
    INNER JOIN ld_variedades AS v ON v.nombre = p.variedad
    INNER JOIN ld_colores AS c ON c.codigo = v.codgcol
    WHERE p.plantas > 0
      AND p.temporada != 'VITRI'
    GROUP BY p.producto, c.orden, c.nombre, p.variedad, p.finca
    ORDER BY p.producto,c.orden, p.variedad, finca
"""

QUALITY_COLUMN_MAP = {
    "SELECT": "SEL",
    "FAN": "FAN",
    "STD": "STD",
    "SHR": "SHR",
    "NAL": "NAL",
}

QUALITY_COLUMNS = ["SEL", "FAN", "STD", "SHR", "NAL"]
FUSARIUM_COLUMN = "Fusarium"
CYCLE_COLUMN = "ciclo"
PEAK_COLUMN = "Pico"
ALL_FARMS_CODE = "000"


def _normalize_variedad_key(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper()


def _append_all_farms_base_rows(df_base: pd.DataFrame) -> pd.DataFrame:
    if df_base.empty:
        return df_base

    grouped = (
        df_base.sort_values(["_orden_fila", "finca"], kind="stable")
        .groupby(["flor", "orden_color", "color", "variedad", "merge_variedad"], as_index=False)
        .agg({"_orden_fila": "min"})
    )
    grouped["finca"] = ALL_FARMS_CODE
    return pd.concat([df_base, grouped[df_base.columns]], ignore_index=True)


def _load_productivities_base() -> pd.DataFrame:
    rows = execute_query(PRODUCTIVITIES_BASE_QUERY) or []
    df_base = pd.DataFrame(rows, columns=["flor", "orden_color", "color", "variedad", "finca"])
    if df_base.empty:
        raise RuntimeError("No se encontraron registros base en plane para construir el reporte de productividades.")

    df_base["orden_color"] = pd.to_numeric(df_base["orden_color"], errors="coerce")
    df_base["finca"] = normalize_finca_series(df_base["finca"])
    df_base["merge_variedad"] = _normalize_variedad_key(df_base["variedad"])
    df_base["_orden_fila"] = range(len(df_base))
    return _append_all_farms_base_rows(df_base)


def _load_production_summary() -> pd.DataFrame:
    source_path = Path(normalize_path(settings.CURVAS_PRODUCCION_RESUMEN_OUTPUT_PATH))
    if not source_path.exists():
        raise FileNotFoundError(
            f"No existe el resumen de production: {source_path}. Ejecuta primero el job 'production_pipeline_curvas'."
        )

    df_prod = pd.read_csv(source_path, dtype={"finca": str})
    if df_prod.empty:
        raise RuntimeError("El resumen de production no contiene datos.")

    validate_columns(df_prod, {"finca", "nvariedad", "ciclo", "f_m", "pico"}, source_path.name)
    df_prod["finca"] = normalize_finca_series(df_prod["finca"])
    df_prod["merge_variedad"] = _normalize_variedad_key(df_prod["nvariedad"])
    df_prod["ciclo"] = pd.to_numeric(df_prod["ciclo"], errors="coerce").astype("Int64")
    df_prod["f_m"] = pd.to_numeric(df_prod["f_m"], errors="coerce")
    df_prod["pico"] = pd.to_numeric(df_prod["pico"], errors="coerce")

    df_prod = df_prod.dropna(subset=["ciclo"]).copy()
    if df_prod.empty:
        raise RuntimeError("El resumen de production no tiene ciclos válidos para cruzar.")

    return df_prod[["finca", "merge_variedad", "ciclo", "f_m", "pico"]].copy()


def _load_qualities_summary() -> pd.DataFrame:
    source_path = Path(normalize_path(settings.CALIDADES_OUTPUT_PATH))
    if not source_path.exists():
        raise FileNotFoundError(
            f"No existe el resumen de calidades: {source_path}. Ejecuta primero el job 'qualities_pipeline'."
        )

    df_qualities = pd.read_csv(source_path, dtype={"finca": str})
    if df_qualities.empty:
        raise RuntimeError("El resumen de calidades no contiene datos.")

    validate_columns(df_qualities, {"finca", "nvari", "grado", "aporte"}, source_path.name)
    df_qualities["finca"] = normalize_finca_series(df_qualities["finca"])
    df_qualities["merge_variedad"] = _normalize_variedad_key(df_qualities["nvari"])
    df_qualities["grado"] = df_qualities["grado"].astype(str).str.strip().str.upper().replace(QUALITY_COLUMN_MAP)
    df_qualities["aporte"] = pd.to_numeric(df_qualities["aporte"], errors="coerce").fillna(0) * 100

    df_qualities = df_qualities[df_qualities["grado"].isin(QUALITY_COLUMNS)].copy()
    if df_qualities.empty:
        raise RuntimeError("No se encontraron grados válidos para el reporte de calidades.")

    df_qualities = (
        df_qualities.pivot_table(
            index=["finca", "merge_variedad"],
            columns="grado",
            values="aporte",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
    )
    df_qualities.columns.name = None

    for grade in QUALITY_COLUMNS:
        if grade not in df_qualities.columns:
            df_qualities[grade] = 0

    df_qualities[QUALITY_COLUMNS] = df_qualities[QUALITY_COLUMNS].round(0).astype("Int64")
    return df_qualities[["finca", "merge_variedad", *QUALITY_COLUMNS]].copy()


def _load_fusarium_summary() -> pd.DataFrame:
    source_path = Path(normalize_path(settings.FUSARIUM_VARIETIES_OUTPUT_PATH))
    if not source_path.exists():
        raise FileNotFoundError(
            f"No existe el resumen de fusarium: {source_path}. Ejecuta primero el job 'fusarium_pipeline'."
        )

    df_fusarium = pd.read_csv(source_path, dtype={"finca": str})
    if df_fusarium.empty:
        raise RuntimeError("El resumen de fusarium no contiene datos.")

    validate_columns(df_fusarium, {"finca", "variedad", "ciclo", "fusarium"}, source_path.name)
    df_fusarium["finca"] = normalize_finca_series(df_fusarium["finca"])
    df_fusarium["merge_variedad"] = _normalize_variedad_key(df_fusarium["variedad"])
    df_fusarium["ciclo"] = pd.to_numeric(df_fusarium["ciclo"], errors="coerce").astype("Int64")
    df_fusarium["fusarium"] = pd.to_numeric(df_fusarium["fusarium"], errors="coerce").round(1)
    df_fusarium = df_fusarium.dropna(subset=["ciclo", "fusarium"]).copy()
    if df_fusarium.empty:
        raise RuntimeError("El resumen de fusarium no tiene ciclos válidos para cruzar.")

    return df_fusarium[["finca", "merge_variedad", "ciclo", "fusarium"]].copy()


def _build_cycle_rows(df_base: pd.DataFrame, df_prod: pd.DataFrame, df_fusarium: pd.DataFrame) -> pd.DataFrame:
    df_cycles = pd.merge(
        df_base,
        df_prod,
        on=["finca", "merge_variedad"],
        how="left",
        sort=False,
    )
    df_cycles = pd.merge(
        df_cycles,
        df_fusarium,
        on=["finca", "merge_variedad", "ciclo"],
        how="left",
        sort=False,
    )
    df_cycles = df_cycles.dropna(subset=["ciclo"]).copy()
    df_cycles[CYCLE_COLUMN] = df_cycles["ciclo"].astype("Int64").astype(str)
    df_cycles["Flor Mata"] = pd.to_numeric(df_cycles["f_m"], errors="coerce").round(2)
    df_cycles[PEAK_COLUMN] = pd.to_numeric(df_cycles["pico"], errors="coerce").round().astype("Int64")
    df_cycles["row_order"] = df_cycles["ciclo"].astype("Int64")
    df_cycles[FUSARIUM_COLUMN] = pd.to_numeric(df_cycles["fusarium"], errors="coerce").round(1)

    for grade in QUALITY_COLUMNS:
        df_cycles[grade] = pd.NA

    return df_cycles[["flor", "color", "finca", CYCLE_COLUMN, PEAK_COLUMN, "variedad", "Flor Mata", *QUALITY_COLUMNS, FUSARIUM_COLUMN, "_orden_fila", "row_order"]]


def _build_total_rows(df_base: pd.DataFrame, df_prod: pd.DataFrame, df_qualities: pd.DataFrame) -> pd.DataFrame:
    df_total = (
        df_prod.groupby(["finca", "merge_variedad"], as_index=False)
        .agg({"f_m": "sum"})
    )
    df_total = pd.merge(
        df_base,
        df_total,
        on=["finca", "merge_variedad"],
        how="left",
        sort=False,
    )
    df_total = pd.merge(
        df_total,
        df_qualities,
        on=["finca", "merge_variedad"],
        how="left",
        sort=False,
    )
    df_total = df_total.drop_duplicates(subset=["finca", "merge_variedad"], keep="first").copy()
    df_total[CYCLE_COLUMN] = "Total"
    df_total[PEAK_COLUMN] = pd.NA
    df_total["Flor Mata"] = pd.to_numeric(df_total["f_m"], errors="coerce").round(2)
    df_total["row_order"] = 3
    df_total[FUSARIUM_COLUMN] = pd.NA

    for grade in QUALITY_COLUMNS:
        if grade not in df_total.columns:
            df_total[grade] = pd.NA

    return df_total[["flor", "color", "finca", CYCLE_COLUMN, PEAK_COLUMN, "variedad", "Flor Mata", *QUALITY_COLUMNS, FUSARIUM_COLUMN, "_orden_fila", "row_order"]]


def generate_productivity_varieties_report(params: dict | None = None) -> str:
    del params

    df_base = _load_productivities_base()
    df_prod = _load_production_summary()
    df_qualities = _load_qualities_summary()
    df_fusarium = _load_fusarium_summary()

    df_cycles = _build_cycle_rows(df_base=df_base, df_prod=df_prod, df_fusarium=df_fusarium)
    df_total = _build_total_rows(df_base=df_base, df_prod=df_prod, df_qualities=df_qualities)
    df_report = pd.concat([df_cycles, df_total], ignore_index=True)
    df_report["finca_order"] = df_report["finca"].map({"001": 1, "002": 2, ALL_FARMS_CODE: 3}).fillna(99)
    df_report = df_report.sort_values(["_orden_fila", "finca_order", "row_order"]).reset_index(drop=True)
    df_report["finca"] = normalize_finca_series(df_report["finca"])
    df_report = df_report.rename(columns={"color": "gcolor", "variedad": "nvariedad"})
    df_report = df_report[["flor", "gcolor", "finca", CYCLE_COLUMN, "nvariedad", PEAK_COLUMN, "Flor Mata", *QUALITY_COLUMNS, FUSARIUM_COLUMN]].copy()

    output_path = Path(normalize_path(settings.PRODUCTIVIDADES_OUTPUT_PATH))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df_report.to_excel(writer, index=False, sheet_name="productividades")
        worksheet = writer.sheets["productividades"]
        finca_col = df_report.columns.get_loc("finca") + 1
        peak_col = df_report.columns.get_loc(PEAK_COLUMN) + 1
        flor_mata_col = df_report.columns.get_loc("Flor Mata") + 1
        grade_cols = [df_report.columns.get_loc(grade) + 1 for grade in QUALITY_COLUMNS]
        fusarium_col = df_report.columns.get_loc(FUSARIUM_COLUMN) + 1
        for cell in worksheet.iter_cols(min_col=finca_col, max_col=finca_col, min_row=2, max_row=worksheet.max_row):
            for finca_cell in cell:
                if finca_cell.value is None:
                    continue
                finca_cell.value = str(finca_cell.value).zfill(3)
                finca_cell.number_format = "@"
        for cell in worksheet.iter_cols(min_col=flor_mata_col, max_col=flor_mata_col, min_row=2, max_row=worksheet.max_row):
            for flor_mata_cell in cell:
                if flor_mata_cell.value is None:
                    continue
                flor_mata_cell.number_format = "0.00"
        for cell in worksheet.iter_cols(min_col=peak_col, max_col=peak_col, min_row=2, max_row=worksheet.max_row):
            for peak_cell in cell:
                if peak_cell.value is None:
                    continue
                peak_cell.number_format = "0"
        for grade_col in grade_cols:
            for cell in worksheet.iter_cols(min_col=grade_col, max_col=grade_col, min_row=2, max_row=worksheet.max_row):
                for grade_cell in cell:
                    if grade_cell.value is None:
                        continue
                    grade_cell.number_format = "0"
        for cell in worksheet.iter_cols(min_col=fusarium_col, max_col=fusarium_col, min_row=2, max_row=worksheet.max_row):
            for fusarium_cell in cell:
                if fusarium_cell.value is None:
                    continue
                fusarium_cell.number_format = "0.0"
    return str(output_path)