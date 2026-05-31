from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.settings import settings
from app.services.utils.dbf_reader import normalize_path
from app.services.etl.helpers import execute_query, pico, safe_int_series, validate_columns


FLOWER_MAP: dict[str, str] = {
    "CLAVEL": "CLA",
    "MINICLAVEL": "CM0",
    "MINI": "CM0",
    "CLA": "CLA",
    "CM0": "CM0",
}

COLOR_REPLACEMENTS: dict[str, str] = {
    "MEDIUM PINK": "ROSADO",
    "LIGHT PINK": "ROSADO",
    "BABY PINK": "ROSADO",
}

FINAL_COLUMNS: list[str] = [
    "finca",
    "flor",
    "bloque",
    "cosecha",
    "variedad",
    "fecha",
    "edad",
    "tipo",
    "color",
    "matas",
    "tallos",
    "pico",
    "ncosecha",
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(" ", "_", regex=False)
        .str.replace("-", "_", regex=False)
    )
    return df


def _normalize_text(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.replace(" ", "_", regex=False)


def _normalize_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.normalize()


def _ajustar_a_lunes(series: pd.Series) -> pd.Series:
    fechas = _normalize_date(series)
    return fechas - pd.to_timedelta(fechas.dt.weekday.fillna(0), unit="D")


def _compute_pico(series: pd.Series) -> pd.Series:
    """Apply pico() from etl_helpers element-wise; NaN → 0."""
    return pd.to_numeric(series.apply(pico), errors="coerce").fillna(0).astype(int)


# ---------------------------------------------------------------------------
# data loaders
# ---------------------------------------------------------------------------

def _load_db_picos() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (df_dates, df_vari, df_season) from the database."""
    rows_dates = execute_query(
        "SELECT aass, fecha, año, mes, semana FROM dates WHERE dia_semana=1"
    ) or []
    df_dates = pd.DataFrame(rows_dates, columns=["aass", "fecha", "año", "mes", "semana"])
    if df_dates.empty:
        raise RuntimeError("No se encontraron fechas lunes en la tabla dates.")
    df_dates["aass"] = safe_int_series(df_dates["aass"]).astype(int)
    df_dates["fecha"] = _normalize_date(df_dates["fecha"])

    rows_vari = execute_query(
        """
        SELECT v.nombre AS variedad, c.nombre AS color, v.codflor AS flor
        FROM ld_variedades AS v
        INNER JOIN ld_colores AS c ON c.codigo = v.codgcol
        WHERE v.codflor IN ('CLA','CM0') AND v.activo = 1
        """
    ) or []
    df_vari = pd.DataFrame(rows_vari, columns=["variedad", "color", "flor"])
    if df_vari.empty:
        raise RuntimeError("No se encontraron variedades activas para CLA/CM0.")
    df_vari["variedad"] = _normalize_text(df_vari["variedad"])
    df_vari["color"] = _normalize_text(df_vari["color"])
    df_vari["flor"] = df_vari["flor"].astype(str).str.strip()

    rows_season = execute_query(
        """
        SELECT cod_temporada AS cosecha,
               CONCAT(fiesta, RIGHT(YEAR(fecha_pico), 2)) AS ncosecha
        FROM seasons
        """
    ) or []
    df_season = pd.DataFrame(rows_season, columns=["cosecha", "ncosecha"])

    return df_dates, df_vari, df_season


def _load_proyecciones_picos() -> pd.DataFrame:
    """
    Lee proyecciones.csv, renombra ncolor→color, aplica el factor de tallos y
    calcula pico desde edad.  Devuelve un DataFrame con FINAL_COLUMNS.
    """
    path = Path(normalize_path(settings.PROYECCIONES_OUTPUT_PATH))
    if not path.exists():
        raise FileNotFoundError(
            "No existe proyecciones.csv. Ejecuta primero el job 'proyecciones_csv'."
        )
    df = pd.read_csv(path, low_memory=False)
    df = _normalize_columns(df)

    if "ncolor" in df.columns and "color" not in df.columns:
        df = df.rename(columns={"ncolor": "color"})
    if "nvari" in df.columns and "variedad" not in df.columns:
        df = df.rename(columns={"nvari": "variedad"})

    required = {"finca", "flor", "bloque", "variedad", "cosecha", "fecha", "matas", "edad", "tipo", "tallos", "color"}
    validate_columns(df, required, path.name)

    df["fecha"] = _normalize_date(df["fecha"])
    df["variedad"] = _normalize_text(df["variedad"])
    df["color"] = _normalize_text(df["color"])
    df["flor"] = df["flor"].astype(str).str.strip().replace(FLOWER_MAP)
    df["tallos"] = pd.to_numeric(df["tallos"], errors="coerce").fillna(0) * settings.PICOS_TALLOS_FACTOR
    df["matas"] = pd.to_numeric(df["matas"], errors="coerce")
    df["edad"] = pd.to_numeric(df["edad"], errors="coerce")
    df["tipo"] = df["tipo"].astype(str).str.strip()
    df["finca"] = df["finca"].astype(str).str.strip()

    df["pico"] = _compute_pico(df["edad"])

    if "ncosecha" not in df.columns:
        df["ncosecha"] = np.nan

    for col in FINAL_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    return df[FINAL_COLUMNS].copy()


def _load_quipus_picos(df_dates: pd.DataFrame, df_vari: pd.DataFrame) -> pd.DataFrame:
    """
    Lee quipus.csv (output del job 'quipus_vs_proy').
    Como ese CSV no incluye 'edad' ni 'color', los complementa desde df_vari y
    asigna pico=0 (sin información de edad).
    """
    path = Path(normalize_path(settings.QUIPUS_OUTPUT_PATH))
    if not path.exists():
        raise FileNotFoundError(
            "No existe quipus.csv. Ejecuta primero el job 'quipus_vs_proy'."
        )
    df = pd.read_csv(path, thousands=",", dtype={"finca": str}, low_memory=False)
    df = _normalize_columns(df)

    if "cantidad" in df.columns and "tallos" not in df.columns:
        df = df.rename(columns={"cantidad": "tallos"})
    if "nfiesta" in df.columns and "ncosecha" not in df.columns:
        df = df.rename(columns={"nfiesta": "ncosecha"})

    validate_columns(df, {"finca", "flor", "bloque", "cosecha", "variedad", "sem_prod", "tallos"}, path.name)

    df["variedad"] = _normalize_text(df["variedad"])
    df["flor"] = df["flor"].astype(str).str.strip().replace(FLOWER_MAP)
    df["tallos"] = pd.to_numeric(df["tallos"], errors="coerce").fillna(0)
    df["matas"] = 0

    # edad: no presente en el CSV actual; pico queda en 0
    if "edad" not in df.columns:
        df["edad"] = np.nan
    else:
        df["edad"] = pd.to_numeric(df["edad"], errors="coerce")
    df["pico"] = _compute_pico(df["edad"])

    # color: obtener desde df_vari si no está en el CSV
    if "color" not in df.columns:
        df = pd.merge(
            df,
            df_vari[["variedad", "flor", "color"]],
            on=["variedad", "flor"],
            how="left",
        )
    else:
        df["color"] = _normalize_text(df["color"])

    # sem_prod → fecha via df_dates
    df["sem_prod"] = safe_int_series(df["sem_prod"]).astype(int)
    df = pd.merge(
        df,
        df_dates[["aass", "fecha"]].rename(columns={"aass": "sem_prod"}),
        on="sem_prod",
        how="left",
    ).drop(columns=["sem_prod"])

    if "tipo" not in df.columns:
        df["tipo"] = "quipus"
    if "ncosecha" not in df.columns:
        df["ncosecha"] = np.nan

    for col in FINAL_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    return df[FINAL_COLUMNS].copy()


def _process_tika_picos(
    modelo: int,
    tipo: str,
    df_dates: pd.DataFrame,
    df_season: pd.DataFrame,
) -> pd.DataFrame:
    """
    Lee proy1.csv + proy2.csv del modelo Tika indicado, agrega por
    finca / bloque / cosecha / variedad / semana / edad / color / ciclo,
    fusiona con fechas y temporadas.  Devuelve un DataFrame con FINAL_COLUMNS.
    """
    tika_dir = f"//svrinverpalmas/Usuarios/Hilder/Data/tika/{modelo}"
    frames: list[pd.DataFrame] = []
    for fname in ("proy1.csv", "proy2.csv"):
        path = Path(normalize_path(f"{tika_dir}/{fname}"))
        if not path.exists():
            raise FileNotFoundError(
                f"No existe archivo Tika para modelo {modelo}: {path}"
            )
        frames.append(pd.read_csv(path, thousands=",", low_memory=False))

    df = pd.concat(frames, ignore_index=True)
    df = _normalize_columns(df).fillna(0)

    validate_columns(
        df,
        {"finca", "flor", "bloque", "cosecha", "variedad", "semanaproducion", "edad", "color", "ciclo", "cantidadsembrada", "cantidad"},
        f"tika/{modelo}/proy1|proy2",
    )

    df = (
        df.groupby(
            ["finca", "flor", "bloque", "cosecha", "variedad", "semanaproducion", "edad", "color", "ciclo"],
            dropna=False,
        )
        .agg({"cantidadsembrada": np.sum, "cantidad": np.sum})
        .reset_index()
    )

    # fusionar con fechas
    df["semanaproducion"] = pd.to_numeric(df["semanaproducion"], errors="coerce").astype("Int64")
    df = pd.merge(
        df,
        df_dates[["aass", "fecha"]].rename(columns={"aass": "semanaproducion"}),
        on="semanaproducion",
        how="left",
    ).drop(columns=["semanaproducion"])

    df["tipo"] = tipo
    df["flor"] = df["flor"].astype(str).str.strip().replace(FLOWER_MAP)
    df["finca"] = np.where(df["finca"].astype(str).str.upper() == "INVERPALMAS", "001", "002")

    df = df.rename(columns={
        "cantidad": "tallos",
        "cantidadsembrada": "matas",
        "ciclo": "pico",
    })

    df["variedad"] = _normalize_text(df["variedad"])
    df["color"] = _normalize_text(df["color"])
    df["edad"] = pd.to_numeric(df["edad"], errors="coerce")
    df["tallos"] = pd.to_numeric(df["tallos"], errors="coerce").fillna(0)
    df["matas"] = pd.to_numeric(df["matas"], errors="coerce")
    df["pico"] = pd.to_numeric(df["pico"], errors="coerce").fillna(0).astype(int)

    # ncosecha desde tabla seasons
    df = pd.merge(df, df_season, on="cosecha", how="left")
    if "ncosecha" not in df.columns:
        df["ncosecha"] = np.nan

    for col in FINAL_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    return df[FINAL_COLUMNS].copy()


def _load_demanda_picos(df_dates: pd.DataFrame, df_vari: pd.DataFrame) -> pd.DataFrame:
    """
    Lee el CSV de demanda, normaliza y devuelve un DataFrame con FINAL_COLUMNS.
    Las columnas de granularidad de bloque/finca/cosecha quedan en NaN ya que
    la demanda no tiene esa resolución.
    """
    path = Path(normalize_path(settings.PICOS_DEMANDA_PATH))
    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo de demanda: {path}")

    df = pd.read_csv(path, thousands=".")
    df = _normalize_columns(df)
    validate_columns(df, {"semana", "item_demanda", "cantidad"}, path.name)

    df = df[["semana", "item_demanda", "precio", "cantidad", "submercado"]].copy()
    df["cantidad"] = df["cantidad"].replace({",": ""}, regex=True)
    df["tallos"] = pd.to_numeric(df["cantidad"], errors="coerce").astype("Int64")
    df = df.rename(columns={"semana": "aass", "item_demanda": "variedad"})
    df["aass"] = pd.to_numeric(df["aass"].astype(str), errors="coerce").astype("Int64")
    df["variedad"] = _normalize_text(df["variedad"])

    # flor + color from variedades catalog
    df = pd.merge(df, df_vari, on="variedad", how="left")
    df["tipo"] = "demanda"

    # fecha desde dates
    df = pd.merge(
        df,
        df_dates[["fecha", "aass"]],
        on="aass",
        how="left",
    ).drop(columns=["aass"])

    # ajustar a lunes
    df["fecha"] = _ajustar_a_lunes(df["fecha"])

    # columns sin resolución de bloque
    df["edad"] = np.nan
    df["matas"] = np.nan
    df["bloque"] = np.nan
    df["finca"] = np.nan
    df["cosecha"] = np.nan
    df["ncosecha"] = np.nan
    df["pico"] = 0

    return df[FINAL_COLUMNS].copy()


# ---------------------------------------------------------------------------
# secondary analysis
# ---------------------------------------------------------------------------

def _generate_diferencias(df_export: pd.DataFrame, params: dict[str, Any]) -> None:
    """
    Calcula flor_color_diferencias.csv con la diferencia entre producción
    proyectada (Real|Teo) y demanda, por flor/color/semana.
    """
    from app.services.utils.date_service import get_current_iso_week

    semana_actual = int(params.get("semana_actual") or get_current_iso_week())
    semana_inicio = int(params.get("semana_inicio") or settings.PICOS_SEMANA_INICIO)
    semana_fin = int(params.get("semana_fin") or settings.PICOS_SEMANA_FIN)

    df_real1 = df_export.query(
        "tipo == 'Real' and (aass >= @semana_inicio and aass < @semana_actual)"
    )
    df_proy1 = df_export.query(
        "tipo == 'Proy_Aj' and (aass >= @semana_actual and aass <= @semana_fin)"
    )
    df_proy_real = pd.concat([df_real1, df_proy1], ignore_index=True)
    df_proy_real = df_proy_real.copy()
    df_proy_real["tipo"] = "Real|Teo"

    df_demanda1 = df_export.query(
        "tipo == 'demanda' and (aass >= @semana_inicio and aass <= @semana_fin)"
    )
    df_proy_real_dem = pd.concat([df_proy_real, df_demanda1], ignore_index=True)

    df_proy_real_dem["tipo"] = pd.Categorical(
        df_proy_real_dem["tipo"], categories=["Real|Teo", "demanda"]
    )

    df_prd = (
        df_proy_real_dem
        .query("flor in ['CLA', 'CM0']")
        .groupby(["flor", "color", "aass", "tipo"], observed=False)["tallos"]
        .sum()
        .unstack("tipo", fill_value=0)
        .reset_index()
    )
    df_prd.columns.name = None

    if "demanda" in df_prd.columns and "Real|Teo" in df_prd.columns:
        df_prd["aporte_color_demanda"] = df_prd.groupby(["flor", "aass"])["demanda"].transform(
            lambda x: x / x.sum() if x.sum() != 0 else 0.0
        )
        df_prd["aporte_color_Real|Teo"] = df_prd.groupby(["flor", "aass"])["Real|Teo"].transform(
            lambda x: x / x.sum() if x.sum() != 0 else 0.0
        )
        df_prd["diferencia"] = df_prd["Real|Teo"] - df_prd["demanda"]

    diferencias_path = Path(normalize_path(settings.PICOS_OUTPUT_DIFERENCIAS_PATH))
    diferencias_path.parent.mkdir(parents=True, exist_ok=True)
    df_prd.to_csv(diferencias_path, index=False, encoding="utf-8-sig")


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------

def generate_comparar_picos_demanda_report(params: dict[str, Any] | None = None) -> str:
    """
    Genera compara_pto_proy_real.csv y flor_color_diferencias.csv consolidando:
    - proyecciones.csv  (factor 0.9, pico desde edad)
    - quipus.csv        (salida de quipus_vs_proy)
    - Tika proy1+proy2  (modelo configurable, default 485)
    - demanda CSV       (demanda_*.csv de la red)

    Params opcionales:
      modelo_tika   (int)  – modelo Tika a usar, default settings.PICOS_TIKA_MODELO
      semana_actual (int)  – corte Real vs Proy_Aj en el reporte diferencias
      semana_inicio (int)  – inicio ventana en reporte diferencias
      semana_fin    (int)  – fin ventana en reporte diferencias
    """
    params = params or {}
    modelo_tika = int(params.get("modelo_tika") or settings.PICOS_TIKA_MODELO)

    df_dates, df_vari, df_season = _load_db_picos()

    df_proy = _load_proyecciones_picos()
    df_quipus = _load_quipus_picos(df_dates, df_vari)
    df_tika = _process_tika_picos(modelo_tika, "tika", df_dates, df_season)
    df_demanda = _load_demanda_picos(df_dates, df_vari)

    df = pd.concat([df_proy, df_demanda, df_tika, df_quipus], ignore_index=True)

    df["edad"] = pd.to_numeric(df["edad"], errors="coerce").astype("Int64")
    df["bloque"] = pd.to_numeric(df["bloque"], errors="coerce").astype("Int64")
    df["matas"] = pd.to_numeric(df["matas"], errors="coerce")
    df["fecha"] = pd.to_datetime(df["fecha"])

    # fusionar con dimensión calendario
    df_export = pd.merge(df, df_dates, on="fecha", how="left")
    df_export["fecha"] = pd.to_datetime(df_export["fecha"], errors="coerce").dt.normalize()
    df_export["pico"] = pd.to_numeric(df_export["pico"], errors="coerce").fillna(0).astype(int)

    # separar _ con espacio para presentación
    df_export["variedad"] = df_export["variedad"].str.replace("_", " ", regex=False)
    df_export["color"] = df_export["color"].astype(str).str.replace("_", " ", regex=False)

    # reemplazos de color
    df_export["color"] = df_export["color"].replace(COLOR_REPLACEMENTS)

    # guardar CSV principal
    output_path = Path(normalize_path(settings.PICOS_OUTPUT_PATH))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_export.to_csv(output_path, index=False, encoding="utf-8-sig")

    # reporte secundario (diferencias por color)
    _generate_diferencias(df_export, params)

    return str(output_path)
