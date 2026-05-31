from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.settings import settings
from app.services.etl.helpers import (
    create_date_table,
    create_month_period_table,
    read_dbf,
    read_many_dbf,
    safe_int_series,
    validate_columns,
)


def generate_bajas_exportado_reports() -> str:
    date_dim = create_date_table("2010-01-01", "2026-11-02")
    date_dim_month = create_month_period_table(date_dim)
    date_dim = date_dim[["año", "mes", "fecha", "semana"]]

    exportado_path = r"\\svrinverpalmas\produc\basetdinamica\exportado.dbf"
    df_exp = read_dbf(exportado_path)
    if df_exp.empty:
        raise RuntimeError("El archivo exportado.dbf no contiene datos.")

    validate_columns(df_exp, {"ano", "mes", "flor", "expble"}, "exportado.dbf")

    df_exp["periodo"] = (
        safe_int_series(df_exp["ano"]).astype(int).astype(str).str.zfill(4)
        + safe_int_series(df_exp["mes"]).astype(int).astype(str).str.zfill(2)
    )
    df_exp["flor"] = df_exp["flor"].astype(str).str.strip()
    df_exp["expble"] = safe_int_series(df_exp["expble"])

    docu_files = [f"docu{year}.dbf" for year in range(2010, 2027)]
    df_docu = read_many_dbf(r"\\svrinverpalmas\produc\ld_bcult", docu_files)
    if df_docu.empty:
        raise RuntimeError("No se encontraron datos en archivos docuYYYY.dbf.")

    validate_columns(
        df_docu,
        {"fecha", "tipo", "flor", "grado1", "grado2", "causa", "variedad", "ramos", "tallos"},
        "docu*.dbf",
    )

    df_docu["fecha"] = pd.to_datetime(df_docu["fecha"], errors="coerce")
    df_docu = df_docu[df_docu["fecha"].notna()].copy()

    cond_tipo001_filtrado = (
        (df_docu["tipo"].astype(str).str.strip() == "001")
        & (df_docu["grado1"].astype(str).str.strip() != "NAL")
        & (df_docu["grado2"].astype(str).str.strip() == "NAL")
    )
    cond_tipo010_todos = (
        (df_docu["tipo"].astype(str).str.strip() == "010")
        & (df_docu["grado2"].astype(str).str.strip() == "NAL")
    )
    cond_flores = df_docu["flor"].astype(str).str.strip().isin(["CLA", "CM0", "ROC", "ROS"])
    mask = (cond_tipo001_filtrado | cond_tipo010_todos) & cond_flores

    df_filtered = df_docu.loc[mask].copy()
    if df_filtered.empty:
        raise RuntimeError("El filtro no produjo datos para bajas.")

    df_filtered["ramos"] = safe_int_series(df_filtered["ramos"])
    df_filtered["tallos"] = safe_int_series(df_filtered["tallos"])
    df_filtered["ttallos"] = df_filtered["ramos"] * df_filtered["tallos"]

    df_filtered = pd.merge(df_filtered, date_dim, on="fecha", how="left")

    df_jl = (
        df_filtered.groupby(
            ["tipo", "flor", "variedad", "grado1", "grado2", "causa", "fecha", "año", "mes", "semana"],
            dropna=False,
        )["ttallos"]
        .sum()
        .reset_index()
    )

    df_monthly = (
        df_filtered.groupby(["flor", "año", "mes"], dropna=False)["ttallos"]
        .sum()
        .reset_index()
    )
    df_monthly["periodo"] = (
        safe_int_series(df_monthly["año"]).astype(int).astype(str).str.zfill(4)
        + safe_int_series(df_monthly["mes"]).astype(int).astype(str).str.zfill(2)
    )

    df_bajas = (
        df_monthly.groupby(["flor", "periodo"], dropna=False)["ttallos"]
        .sum()
        .reset_index()
        .rename(columns={"ttallos": "bajas"})
    )

    df_exp_grouped = (
        df_exp.groupby(["periodo", "flor"], dropna=False)["expble"]
        .sum()
        .reset_index()
    )

    df_end = pd.merge(df_exp_grouped, df_bajas, how="left", on=["flor", "periodo"])

    df_export = pd.merge(df_end, date_dim_month[["periodo", "fecha"]], how="left", on="periodo")
    # Extraer año y mes del campo periodo
    df_export["año"] = df_export["periodo"].astype(str).str[:4]
    df_export["mes"] = df_export["periodo"].astype(str).str[4:6]
    df_export["porc_bajas"] = df_export["bajas"] / df_export["expble"]

    output_dir = Path(settings.EXCEL_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_summary = output_dir / "bajas_por_mes.csv"
    output_detail = output_dir / "bajas_desde_2010.csv"

    df_export.to_csv(output_summary, index=False)
    df_jl.to_csv(output_detail, index=False)

    return f"{output_summary};{output_detail}"
