"""Balance de masas para informes mensuales.

Porta el notebook ``load_tests/consulta a exportado.ipynb``: cruza exportado.dbf
(produccion/exportable/exportado por grado) con lonas, presupuesto (pto),
plantas (pblo) y areas (cre) de ld_bcult, reparte el exportado entre fincas
segun el aporte de lonas tiqueteadas y calcula flor/mata y flor/m2 por finca,
mas la finca sintetica "000" (total empresa).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.settings import settings
from app.services.etl.helpers import read_dbf, read_many_dbf, safe_int_series, validate_columns
from app.services.utils.dbf_reader import normalize_path
from app.services.utils.date_service import get_bogota_now

FINCAS = ("001", "002")
PERIODO_KEYS = ["ano", "mes", "flor", "finca"]

# Columnas de exportado.dbf que se reparten entre fincas segun el aporte de lonas.
COLUMNAS_DISTRIBUIR = [
    "produccion", "expble", "exptdo", "bajas_nac", "compras", "obsequios",
    "vta_nal", "desechos", "inicial", "nacional",
]

PRODUCCION_VS_DESPACHADO_RENAME = {
    "produccion": "tallos_producción",
    "expble": "tallos_exportables",
    "exptdo": "tallos_exportados",
    "bajas_nac": "bajas_nacional",
    "inicial": "inventario",
}


# ---------------------------------------------------------------------------
# Limpieza de fuentes
# ---------------------------------------------------------------------------

def _strip(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def _with_ano_mes(df: pd.DataFrame, fecha_col: str = "fecha") -> pd.DataFrame:
    df = df.copy()
    df["fecha"] = pd.to_datetime(df[fecha_col], errors="coerce")
    df = df[df["fecha"].notna()].copy()
    df["ano"] = df["fecha"].dt.year.astype(int)
    df["mes"] = df["fecha"].dt.month.astype(int)
    return df


def prepare_exportado(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra grados vacios / produccion 0 y calcula %grado y venta nacional."""
    df = df.copy()
    numeric = set(COLUMNAS_DISTRIBUIR) - {"vta_nal"} | {"zusa", "zeuro", "zotros", "bajas_a", "ingnaciona"}
    for col in numeric:
        df[col] = safe_int_series(df[col]) if col in df.columns else 0.0
    df["ano"] = safe_int_series(df["ano"]).astype(int)
    df["mes"] = safe_int_series(df["mes"]).astype(int)
    df["flor"] = _strip(df["flor"])
    df["grado"] = _strip(df["grado"])

    df = df[(df["grado"] != "") & (df["produccion"] > 0)].reset_index(drop=True)
    df["%grado"] = df["produccion"] / df.groupby(["ano", "mes", "flor"])["produccion"].transform("sum")
    df["vta_nal"] = df["ingnaciona"] - (
        df["produccion"] - (df["zusa"] + df["zeuro"] + df["zotros"] - df["bajas_a"])
    )
    return df


def prepare_lonas(dflonas: pd.DataFrame) -> pd.DataFrame:
    """Lonas por ano/mes/flor pivotadas por finca, con el aporte de cada finca."""
    df = _with_ano_mes(dflonas)
    df["finca"] = _strip(df["finca"])
    df["lonas"] = safe_int_series(df["lonas"])
    df_prod = df.pivot_table(
        index=["ano", "mes", "flor"], columns="finca", values="lonas", aggfunc="sum"
    ).reset_index()
    df_prod.columns.name = None
    for finca in FINCAS:
        if finca not in df_prod.columns:
            df_prod[finca] = 0.0
    df_prod = df_prod.fillna(0)
    total = df_prod["001"] + df_prod["002"]
    for finca in FINCAS:
        df_prod[f"aporte{finca}"] = df_prod[finca] / total
    return df_prod


def prepare_presupuesto(dfpto: pd.DataFrame) -> pd.DataFrame:
    df = _with_ano_mes(dfpto, "fecha_p" if "fecha_p" in dfpto.columns else "fecha")
    df["finca"] = _strip(df["finca"])
    df["produccion"] = safe_int_series(df["produccion"])
    return (
        df.groupby(PERIODO_KEYS)["produccion"].sum().reset_index()
        .rename(columns={"produccion": "presupuesto"})
    )


def prepare_matas(dfplantas: pd.DataFrame) -> pd.DataFrame:
    """Plantas del ultimo corte (fecha maxima) de cada flor/finca/ano/mes."""
    df = dfplantas.copy()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df[df["fecha"].notna()].copy()
    df["finca"] = _strip(df["finca"])
    df["matas"] = safe_int_series(df["matas"])
    df = df.groupby(["flor", "finca", "fecha"])["matas"].sum().reset_index()
    df["ano"] = df["fecha"].dt.year.astype(int)
    df["mes"] = df["fecha"].dt.month.astype(int)
    idx_max_fecha = df.groupby(["flor", "finca", "ano", "mes"])["fecha"].idxmax()
    return df.loc[idx_max_fecha].groupby(PERIODO_KEYS)["matas"].sum().reset_index()


def prepare_areas(dfareas: pd.DataFrame) -> pd.DataFrame:
    df = dfareas.copy()
    df["ano"] = safe_int_series(df["ano"]).astype(int)
    df["mes"] = safe_int_series(df["mes"]).astype(int)
    df["finca"] = _strip(df["finca"])
    df["metros"] = safe_int_series(df["metros"])
    return df.groupby(["finca", "flor", "ano", "mes"])["metros"].sum().reset_index()


# ---------------------------------------------------------------------------
# Transformaciones
# ---------------------------------------------------------------------------

def build_produccion_vs_despachado(df: pd.DataFrame) -> pd.DataFrame:
    agg = {col: "sum" for col in COLUMNAS_DISTRIBUIR}
    agg["%grado"] = "mean"
    df1 = df.groupby(["ano", "mes", "flor", "grado"]).agg(agg).reset_index()
    return df1.rename(columns=PRODUCCION_VS_DESPACHADO_RENAME)


def build_real_vs_presupuesto(
    df: pd.DataFrame,
    df_pto: pd.DataFrame,
    anio_desde: int,
    factores_exportable: dict[str, float],
    factor_default: float,
) -> pd.DataFrame:
    """Real (exportado.dbf) vs presupuesto por flor/mes en formato largo (origen/variable/tallos)."""
    real = df.groupby(["ano", "mes", "flor"]).agg({"produccion": "sum", "expble": "sum", "exptdo": "sum"}).reset_index()
    pto = df_pto.groupby(["ano", "mes", "flor"]).agg({"presupuesto": "sum"}).reset_index()
    merged = pd.merge(real, pto, on=["ano", "mes", "flor"], how="outer")
    merged = merged[merged["ano"] >= anio_desde].copy()

    factor = merged["flor"].map(factores_exportable).fillna(factor_default)
    merged["pto_exportable"] = (merged["presupuesto"] * factor).round(0)
    merged = merged.rename(columns={
        "produccion": "real_produccion",
        "expble": "real_exportable",
        "exptdo": "real_exportado",
        "presupuesto": "pto_produccion",
    })

    tidy = merged.melt(id_vars=["ano", "mes", "flor"], var_name="temp_variable", value_name="tallos")
    tidy[["origen", "variable"]] = tidy["temp_variable"].str.split("_", n=1, expand=True)
    tidy = tidy[["ano", "mes", "flor", "origen", "variable", "tallos"]].copy()
    tidy["periodo"] = tidy["ano"].astype(int).astype(str) + tidy["mes"].astype(int).astype(str).str.zfill(2)
    return tidy.reset_index(drop=True)


def distribuir_por_finca(df: pd.DataFrame, df_prod: pd.DataFrame) -> pd.DataFrame:
    """Reparte el exportado (que no trae finca) entre fincas segun el aporte de lonas."""
    df_d = df[["ano", "mes", "flor", "grado", *COLUMNAS_DISTRIBUIR]]
    frames = []
    for finca in FINCAS:
        aporte_col = f"aporte{finca}"
        frame = pd.merge(
            df_d, df_prod[["ano", "flor", "mes", finca, aporte_col]], on=["ano", "flor", "mes"], how="left"
        ).fillna(0).reset_index(drop=True)
        frame[COLUMNAS_DISTRIBUIR] = frame[COLUMNAS_DISTRIBUIR].multiply(frame[aporte_col], axis="index")
        frame = frame.rename(columns={finca: "produccion_bruta"}).drop(columns=[aporte_col])
        frame["finca"] = finca
        frames.append(frame)
    dframe0 = pd.concat(frames, axis=0).fillna(0)
    return dframe0[dframe0["produccion"] > 0]


def _add_ratios(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["%nacional"] = frame["nacional"] / frame["produccion"]
    frame = frame.drop(columns=["nacional"])
    for base in ("produccion", "expble", "exptdo"):
        frame[f"FMata_{base}"] = frame[base] / frame["matas"]
    for base in ("produccion", "expble", "exptdo"):
        frame[f"FM2_{base}"] = frame[base] / frame["metros"]
    return frame.replace([np.inf, -np.inf], np.nan)


def build_base_fincas(
    dframe0: pd.DataFrame,
    df_areas: pd.DataFrame,
    df_pto: pd.DataFrame,
    df_matas: pd.DataFrame,
) -> pd.DataFrame:
    """Base mensual por finca/flor (001, 002 y total 000) con flor/mata y flor/m2."""
    dframe3 = dframe0.merge(df_areas, on=["finca", "flor", "ano", "mes"], how="left")
    dframe3 = dframe3.merge(df_pto, on=["finca", "flor", "ano", "mes"], how="left")
    dframe3 = dframe3.merge(df_matas, on=["finca", "flor", "ano", "mes"], how="left")

    # metros/presupuesto/matas/lonas vienen por finca-flor-mes y se repiten en
    # cada grado; se reparten segun el peso del grado para no duplicarlos al sumar.
    dframe3["aporte"] = dframe3["produccion"] / dframe3.groupby(PERIODO_KEYS)["produccion"].transform("sum")
    cols_multiply = ["produccion_bruta", "metros", "presupuesto", "matas"]
    dframe3[cols_multiply] = dframe3[cols_multiply].multiply(dframe3["aporte"], axis="index")
    dframe3 = dframe3.drop(columns=["grado", "aporte"])

    columnas_a_sumar = dframe3.columns.difference(PERIODO_KEYS)
    dframe4 = dframe3.groupby(PERIODO_KEYS)[columnas_a_sumar].sum().reset_index()

    agg_cols = ["produccion", "expble", "exptdo", "nacional", "matas", "metros", "presupuesto"]
    dframe5 = _add_ratios(dframe4.groupby(["finca", "flor", "ano", "mes"])[agg_cols].sum().reset_index())
    dframe7 = _add_ratios(dframe4.groupby(["flor", "ano", "mes"])[agg_cols].sum().reset_index())
    dframe7["finca"] = "000"
    return pd.concat([dframe5, dframe7], axis=0, ignore_index=True)


def build_datos_exportado(dframe_end: pd.DataFrame) -> pd.DataFrame:
    """Base por finca en formato largo (variable/valor) para el informe mensual."""
    id_vars = ["finca", "flor", "ano", "mes"]
    grupos = [
        ["presupuesto", "produccion", "expble", "exptdo"],
        ["FMata_produccion", "FMata_expble", "FMata_exptdo"],
        ["FM2_produccion", "FM2_expble", "FM2_exptdo"],
    ]
    value_cols = [col for grupo in grupos for col in grupo]
    dframe10 = dframe_end.groupby(id_vars)[value_cols].sum().reset_index()
    return pd.concat(
        [dframe10.melt(id_vars=id_vars, value_vars=grupo, var_name="variable", value_name="valor") for grupo in grupos]
    )


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

def _yearly_files(prefix: str, anio_inicio: int, anio_fin: int) -> list[str]:
    return [f"{prefix}{year}.dbf" for year in range(anio_inicio, anio_fin + 1)]


def _read_areas(base_dir: str, anio_inicio: int, anio_fin: int) -> pd.DataFrame:
    frames = []
    for filename in _yearly_files("cre", anio_inicio, anio_fin):
        frame = read_many_dbf(base_dir, [filename])
        if not frame.empty:
            # cre<año>.dbf no trae el año: se toma del nombre del archivo.
            frame["ano"] = int(filename[3:-4])
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _require(df: pd.DataFrame, columns: set[str], source: str) -> None:
    if df.empty:
        raise RuntimeError(f"No se encontraron datos en {source}.")
    validate_columns(df, columns, source)


def generate_balance_masas(params: dict[str, Any] | None = None) -> str:
    params = params or {}
    anio_inicio = int(params.get("anio_inicio") or settings.BALANCE_MASAS_YEAR_START)
    # Se intenta leer hasta el año siguiente: el presupuesto del año entrante
    # (pto<año+1>.dbf) suele existir antes de que cierre el año en curso. Los
    # archivos que no existan se omiten.
    anio_fin = get_bogota_now().year + 1
    anio_pto_vs_real = int(params.get("anio_pto_vs_real") or settings.BALANCE_MASAS_PTO_VS_REAL_YEAR_START)
    out_dir = Path(normalize_path(params.get("out_dir") or settings.BALANCE_MASAS_OUTPUT_DIR))
    ld_bcult = settings.BALANCE_MASAS_LD_BCULT_DIR

    df_exp = read_dbf(settings.BALANCE_MASAS_EXPORTADO_PATH)
    _require(df_exp, {"ano", "mes", "flor", "grado", "produccion", "expble", "exptdo"}, "exportado.dbf")
    dflonas = read_many_dbf(ld_bcult, _yearly_files("lonas", anio_inicio, anio_fin))
    _require(dflonas, {"fecha", "flor", "finca", "lonas"}, "lonas*.dbf")
    dfpto = read_many_dbf(ld_bcult, _yearly_files("pto", anio_inicio, anio_fin))
    _require(dfpto, {"flor", "finca", "produccion"}, "pto*.dbf")
    dfplantas = read_many_dbf(ld_bcult, _yearly_files("pblo", anio_inicio, anio_fin))
    _require(dfplantas, {"fecha", "flor", "finca", "matas"}, "pblo*.dbf")
    dfareas = _read_areas(ld_bcult, anio_inicio, anio_fin)
    _require(dfareas, {"finca", "flor", "mes", "metros"}, "cre*.dbf")

    df = prepare_exportado(df_exp)
    df_prod = prepare_lonas(dflonas)
    df_pto = prepare_presupuesto(dfpto)
    df_matas = prepare_matas(dfplantas)
    df_areas = prepare_areas(dfareas)

    produccion_vs_despachado = build_produccion_vs_despachado(df)
    real_vs_pto = build_real_vs_presupuesto(
        df,
        df_pto,
        anio_pto_vs_real,
        settings.BALANCE_MASAS_PTO_EXPORTABLE_FACTORES,
        settings.BALANCE_MASAS_PTO_EXPORTABLE_FACTOR_DEFAULT,
    )
    base = build_base_fincas(distribuir_por_finca(df, df_prod), df_areas, df_pto, df_matas)
    datos_exportado = build_datos_exportado(base)

    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "Producción Vs Despachado.xlsx": produccion_vs_despachado,
        "Datos de exportado.xlsx": datos_exportado,
        "Base balance de masas.xlsx": base,
        "datos_realxJI_pto.csv": real_vs_pto,
    }
    written = []
    for filename, frame in outputs.items():
        path = out_dir / filename
        if path.suffix == ".csv":
            frame.to_csv(path, index=False)
        else:
            frame.to_excel(path, index=False)
        written.append(str(path))
    return ";".join(written)
