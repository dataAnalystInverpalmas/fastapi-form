from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from app.core.settings import settings
from app.services.utils.dbf_reader import normalize_path
from app.services.etl.helpers import dataframe_to_sql, execute_query, safe_int_series, validate_columns


FLOWER_MAP = {
    "CLAVEL": "CLA",
    "MINICLAVEL": "CM0",
    "MINI": "CM0",
    "CLA": "CLA",
    "CM0": "CM0",
}

PROYECCIONES_TYPE_MAP = {
    "RE": "Real",
    "REAL": "Real",
    "AJ": "Proy_Aj",
    "PROY_AJ": "Proy_Aj",
    "PROYAJ": "Proy_Aj",
    "IN": "Proy_In",
    "PROY_IN": "Proy_In",
    "PROYIN": "Proy_In",
    "PT": "Pto",
    "PTO": "Pto",
}


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


def _parse_quantity(series: pd.Series) -> pd.Series:
    """Convierte cantidades exportadas por Tika sin importar el separador de miles.

    Según el equipo que exporta, Tika escribe "1,514" o "1.514" para 1514
    (incluso entre carpetas del mismo tipo de archivo). Un valor con grupos
    exactos de 3 dígitos tras ',' o '.' se toma como miles; cualquier otro
    ('914.0', '3,5') se toma como decimal.
    """
    text = series.astype("string").str.strip()
    grouped = text.str.fullmatch(r"-?\d{1,3}(?:,\d{3})+") | text.str.fullmatch(r"-?\d{1,3}(?:\.\d{3})+")
    text = text.where(~grouped.fillna(False), text.str.replace(r"[.,]", "", regex=True))
    text = text.str.replace(",", ".", regex=False)
    return pd.to_numeric(text, errors="coerce").fillna(0)


def _read_tika_csv(path: Path) -> pd.DataFrame:
    """Lee un CSV de Tika como texto; las cantidades se convierten con _parse_quantity."""
    df = _normalize_columns(pd.read_csv(path, dtype=str, encoding="utf-8-sig"))
    if "semana" in df.columns:
        df["semana"] = safe_int_series(df["semana"]).astype(int)
    return df


def _normalize_text(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.replace(" ", "_", regex=False)


def _normalize_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.normalize()


def _ajustar_a_lunes(series: pd.Series) -> pd.Series:
    fechas = _normalize_date(series)
    return fechas - pd.to_timedelta(fechas.dt.weekday.fillna(0), unit="D")


def _load_dates_and_variedades() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows_dates = execute_query(
        "SELECT aass, fecha, año, mes, semana FROM dates WHERE dia_semana=1"
    ) or []
    df_dates = pd.DataFrame(rows_dates, columns=["aass", "fecha", "año", "mes", "semana"])
    if df_dates.empty:
        raise RuntimeError("No se encontraron fechas lunes en la tabla dates.")
    df_dates["aass"] = safe_int_series(df_dates["aass"]).astype(int)
    df_dates["fecha"] = _normalize_date(df_dates["fecha"])
    df_dates["año"] = safe_int_series(df_dates["año"]).astype(int)
    df_dates["mes"] = safe_int_series(df_dates["mes"]).astype(int)
    df_dates["semana"] = safe_int_series(df_dates["semana"]).astype(int)

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
    return df_dates, df_vari


def _model_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA, 27 -> AB... (como columnas de Excel)."""
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


def _resolve_modelos_tika(params: dict[str, Any] | None) -> dict[str, int]:
    """Asigna una letra (A, B, C, ...) a cada modelo segun su posicion.

    Siempre hay al menos 4 modelos (A-D, completados con los defaults);
    los siguientes (E, F, G...) solo aparecen si se envian en modelos_tika.
    """
    defaults = list(settings.COMPARE_TIKA_DEFAULT_MODELS)
    raw_values = list((params or {}).get("modelos_tika") or [])
    parsed = [int(value) for value in raw_values if str(value).strip()]
    if not parsed:
        parsed = defaults
    if len(parsed) < 4:
        parsed = parsed + defaults[len(parsed):4]
    return {_model_letter(i): modelo for i, modelo in enumerate(parsed)}


def _load_proyecciones_compare(df_vari: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    path = Path(normalize_path(settings.PROYECCIONES_OUTPUT_PATH))
    if not path.exists():
        raise FileNotFoundError("No existe proyecciones.csv. Ejecuta primero el job 'proyecciones_csv'.")

    df = pd.read_csv(path, low_memory=False)
    df = _normalize_columns(df)
    required = {"fecha", "flor", "tipo", "tallos", "variedad", "ncolor"}
    if "variedad" not in df.columns and "nvari" in df.columns:
        df = df.rename(columns={"nvari": "variedad"})
    if "ncolor" not in df.columns and "color" in df.columns:
        df = df.rename(columns={"color": "ncolor"})
    validate_columns(df, required, path.name)

    df["fecha"] = _normalize_date(df["fecha"])
    df["variedad"] = _normalize_text(df["variedad"])
    df["color"] = _normalize_text(df["ncolor"])
    df["flor"] = df["flor"].astype(str).str.strip().replace(FLOWER_MAP)
    df["tallos"] = pd.to_numeric(df["tallos"], errors="coerce").fillna(0) * settings.COMPARE_TIKA_TALLOS_FACTOR
    df["tipo"] = df["tipo"].astype(str).str.strip().str.upper().replace(PROYECCIONES_TYPE_MAP)

    base_columns = ["fecha", "flor", "variedad", "color", "tallos", "tipo"]
    df = df[base_columns].copy()
    datos_re = df[df["tipo"] == "Real"].copy()
    datos_in = df[df["tipo"] == "Proy_In"].copy()
    datos_aj = df[df["tipo"] == "Proy_Aj"].copy()
    datos_pt = df[df["tipo"] == "Pto"].copy()
    return datos_re, datos_in, datos_aj, datos_pt


def _load_despachos() -> pd.DataFrame:
    path = Path(normalize_path(settings.COMPARE_TIKA_DESPACHOS_PATH))
    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo de despachos: {path}")
    df = pd.read_excel(path)
    df = _normalize_columns(df)
    validate_columns(df, {"fecha", "flor", "variedad", "color", "tallos", "tipo"}, path.name)
    df["fecha"] = _ajustar_a_lunes(df["fecha"])
    df["flor"] = df["flor"].astype(str).str.strip().replace(FLOWER_MAP)
    df["variedad"] = _normalize_text(df["variedad"])
    df["color"] = _normalize_text(df["color"])
    df["tallos"] = pd.to_numeric(df["tallos"], errors="coerce").fillna(0)
    df["tipo"] = df["tipo"].astype(str).str.strip()
    return df[["fecha", "flor", "variedad", "color", "tallos", "tipo"]].copy()


def _load_quipus_compare(df_dates: pd.DataFrame, df_vari: pd.DataFrame) -> pd.DataFrame:
    path = Path(normalize_path(settings.QUIPUS_OUTPUT_PATH))
    if not path.exists():
        raise FileNotFoundError("No existe quipus.csv. Ejecuta primero el job 'quipus_vs_proy'.")
    df = pd.read_csv(path, low_memory=False)
    df = _normalize_columns(df)
    if "cantidad" in df.columns:
        df = df.rename(columns={"cantidad": "tallos"})
    if "sem_prod" not in df.columns:
        raise ValueError("quipus.csv no contiene la columna sem_prod.")
    validate_columns(df, {"sem_prod", "flor", "variedad", "tallos"}, path.name)
    df["sem_prod"] = safe_int_series(df["sem_prod"]).astype(int)
    df["variedad"] = _normalize_text(df["variedad"])
    df["flor"] = df["flor"].astype(str).str.strip().replace(FLOWER_MAP)
    df["tallos"] = pd.to_numeric(df["tallos"], errors="coerce").fillna(0) * settings.COMPARE_TIKA_TALLOS_FACTOR
    df = pd.merge(df, df_dates[["aass", "fecha"]], left_on="sem_prod", right_on="aass", how="left")
    df = pd.merge(df, df_vari[["variedad", "color", "flor"]], on=["variedad", "flor"], how="left")
    df["tipo"] = "Quipus"
    df = (
        df.groupby(["fecha", "flor", "variedad", "color", "tipo"], dropna=False)["tallos"]
        .sum()
        .reset_index()
    )
    return df[["fecha", "flor", "variedad", "color", "tallos", "tipo"]].copy()


def _process_bajas_perdidas(modelo_tika: int, tipo: str, df_dates: pd.DataFrame, df_vari: pd.DataFrame) -> pd.DataFrame:
    path = Path(normalize_path(f"//172.10.18.2/usuarios/Hilder/Data/tika/{modelo_tika}/guarde.csv"))
    if not path.exists():
        raise FileNotFoundError(f"No existe guarde.csv para modelo Tika {modelo_tika}: {path}")
    df = _read_tika_csv(path).rename(columns={"pérdidas": "perdidas"})
    validate_columns(df, {"semana", "variedad", "bajas", "perdidas"}, path.name)
    df = pd.merge(
        df.rename(columns={"semana": "aass"}),
        df_dates[["fecha", "aass"]],
        on="aass",
        how="left",
    ).drop(columns=["aass"])
    df["tallos"] = _parse_quantity(df["bajas"]) + _parse_quantity(df["perdidas"])
    df["variedad"] = _normalize_text(df["variedad"])
    df = pd.merge(df, df_vari, on="variedad", how="left")
    df["tipo"] = tipo
    df = (
        df.groupby(["fecha", "flor", "variedad", "color", "tipo"], dropna=False)["tallos"]
        .sum()
        .reset_index()
    )
    return df[["fecha", "flor", "variedad", "color", "tallos", "tipo"]].copy()


def _process_salvamento(modelo_tika: int, tipo: str, df_dates: pd.DataFrame, df_vari: pd.DataFrame) -> pd.DataFrame:
    path = Path(normalize_path(f"//172.10.18.2/usuarios/Hilder/Data/tika/{modelo_tika}/salvamento.csv"))
    if not path.exists():
        raise FileNotFoundError(f"No existe salvamento.csv para modelo Tika {modelo_tika}: {path}")
    df = _read_tika_csv(path)
    if "itemdemanda" in df.columns and "item_demanda" not in df.columns:
        df = df.rename(columns={"itemdemanda": "item_demanda"})
    validate_columns(df, {"semana", "cantidad"}, path.name)
    variedad_col = "item_demanda" if "item_demanda" in df.columns else "variedad"
    df = pd.merge(
        df.rename(columns={"semana": "aass"}),
        df_dates[["fecha", "aass"]],
        on="aass",
        how="left",
    ).drop(columns=["aass"])
    df["variedad"] = _normalize_text(df[variedad_col])
    df["tallos"] = _parse_quantity(df["cantidad"])
    df = pd.merge(df, df_vari, on="variedad", how="left")
    df["tipo"] = tipo
    df = (
        df.groupby(["fecha", "flor", "variedad", "color", "tipo"], dropna=False)["tallos"]
        .sum()
        .reset_index()
    )
    return df[["fecha", "flor", "variedad", "color", "tallos", "tipo"]].copy()


def _process_esquejes_futuros(modelo_tika: int, tipo: str, df_dates: pd.DataFrame, df_vari: pd.DataFrame) -> pd.DataFrame:
    """Esquejes (siembra) proyectados por Tika para un modelo/escenario.

    A diferencia de bajas/salvamento, flor/variedad/color vienen directo en
    el archivo (no hay que completarlos desde df_vari).
    """
    path = Path(normalize_path(f"//172.10.18.2/usuarios/Hilder/Data/tika/{modelo_tika}/esquejes_futuros.csv"))
    if not path.exists():
        raise FileNotFoundError(f"No existe esquejes_futuros.csv para modelo Tika {modelo_tika}: {path}")
    df = _read_tika_csv(path)
    validate_columns(df, {"semana", "flor", "variedad", "color", "cantidad"}, path.name)
    df = pd.merge(
        df.rename(columns={"semana": "aass"}),
        df_dates[["fecha", "aass"]],
        on="aass",
        how="left",
    ).drop(columns=["aass"])
    df["flor"] = df["flor"].astype(str).str.strip().replace(FLOWER_MAP)
    df["variedad"] = _normalize_text(df["variedad"])
    df["color"] = _normalize_text(df["color"])
    df["tallos"] = _parse_quantity(df["cantidad"])
    df["tipo"] = tipo
    df = (
        df.groupby(["fecha", "flor", "variedad", "color", "tipo"], dropna=False)["tallos"]
        .sum()
        .reset_index()
    )
    return df[["fecha", "flor", "variedad", "color", "tallos", "tipo"]].copy()


def _process_tika_projection(modelo_tika: int, tipo: str, df_dates: pd.DataFrame, df_vari: pd.DataFrame) -> pd.DataFrame:
    files = [
        Path(normalize_path(f"//172.10.18.2/Usuarios/Hilder/Data/tika/{modelo_tika}/proy1.csv")),
        Path(normalize_path(f"//172.10.18.2/Usuarios/Hilder/Data/tika/{modelo_tika}/proy2.csv")),
        Path(normalize_path(f"//172.10.18.2/Usuarios/Hilder/Data/tika/{modelo_tika}/proy3.csv"))
    ]
    frames: list[pd.DataFrame] = []
    for path in files:
        if not path.exists():
            raise FileNotFoundError(f"No existe archivo Tika de proyeccion para modelo {modelo_tika}: {path}")
        frames.append(pd.read_csv(path, thousands=",", low_memory=False))
    df = pd.concat(frames, ignore_index=True)
    df = _normalize_columns(df)
    validate_columns(df, {"semanaproducion", "variedad", "cantidad"}, f"tika/{modelo_tika}/proy1|proy2.csv")
    df = df.rename(columns={"semanaproducion": "aass"})
    if "flor" in df.columns:
        df["flor"] = df["flor"].astype(str).str.strip().replace(FLOWER_MAP)
    if "color" in df.columns:
        df["color"] = _normalize_text(df["color"])
    df["variedad"] = _normalize_text(df["variedad"])
    df["tallos"] = pd.to_numeric(df["cantidad"], errors="coerce").fillna(0)
    df = pd.merge(df, df_dates[["aass", "fecha"]], on="aass", how="left")
    df = pd.merge(df, df_vari, on="variedad", how="left", suffixes=("", "_db"))
    if "flor_db" in df.columns:
        df["flor"] = df["flor_db"].combine_first(df.get("flor"))
    if "color_db" in df.columns:
        df["color"] = df["color_db"].combine_first(df.get("color"))
    df["tipo"] = tipo
    df = (
        df.groupby(["fecha", "flor", "variedad", "color", "tipo"], dropna=False)["tallos"]
        .sum()
        .reset_index()
    )
    return df[["fecha", "flor", "variedad", "color", "tallos", "tipo"]].copy()


def _load_demanda(df_dates: pd.DataFrame, df_vari: pd.DataFrame) -> pd.DataFrame:
    path = Path(normalize_path(settings.COMPARE_TIKA_DEMANDA_PATH))
    if not path.exists():
        raise FileNotFoundError(f"No existe archivo de demanda: {path}")
    df = pd.read_csv(path, thousands=".")
    df = _normalize_columns(df)
    validate_columns(df, {"semana", "item_demanda", "cantidad"}, path.name)
    df = df[["semana", "item_demanda", "precio", "cantidad", "submercado"]].copy()
    df["cantidad"] = df["cantidad"].replace({",": ""}, regex=True)
    df["tallos"] = pd.to_numeric(df["cantidad"], errors="coerce").astype("Int64")
    df = df.rename(columns={"semana": "aass", "item_demanda": "variedad"})
    df["aass"] = pd.to_numeric(df["aass"], errors="coerce").astype("Int64")
    df["variedad"] = _normalize_text(df["variedad"])
    df = pd.merge(df, df_vari, on="variedad", how="left")
    df["tipo"] = "demanda"
    df = pd.merge(df, df_dates[["fecha", "aass"]], on="aass", how="left").drop(columns=["aass"])
    df = df[df["fecha"].notna()].copy()
    return df[["fecha", "flor", "variedad", "color", "tallos", "tipo"]].copy()


def generate_compare_tika_produccion_report(params: dict[str, Any] | None = None) -> str:
    modelos_tika = _resolve_modelos_tika(params)
    df_dates, df_vari = _load_dates_and_variedades()

    datos_re, datos_in, datos_aj, datos_pt = _load_proyecciones_compare(df_vari)
    df_despachos = _load_despachos()
    df_quipus = _load_quipus_compare(df_dates, df_vari)
    df_demanda = _load_demanda(df_dates, df_vari)

    df_tika = [
        _process_tika_projection(modelo, f"Tika_{letra}", df_dates, df_vari)
        for letra, modelo in modelos_tika.items()
    ]
    df_rota = [
        _process_salvamento(modelo, f"Rota_{letra}", df_dates, df_vari)
        for letra, modelo in modelos_tika.items()
    ]
    df_bajas = [
        _process_bajas_perdidas(modelo, f"Bajas_{letra}", df_dates, df_vari)
        for letra, modelo in modelos_tika.items()
    ]

    #cutoff = pd.Timestamp(settings.COMPARE_TIKA_D_CUTOFF_DATE)
    #df_tika_c = pd.concat([df_tika_d.query("fecha <= @cutoff"), df_tika_c], ignore_index=True)
    #df_tika_c["tipo"] = "Tika_C"
    #df_rota_c = pd.concat([df_rota_d.query("fecha <= @cutoff"), df_rota_c], ignore_index=True)
    #df_rota_c["tipo"] = "Rota_C"
    #df_bajas_c = pd.concat([df_bajas_b.query("fecha <= @cutoff"), df_bajas_c], ignore_index=True)
    #df_bajas_c["tipo"] = "Bajas_C"

    frames = [
        df_despachos,
        df_demanda,
        *df_tika,
        *df_rota,
        *df_bajas,
        datos_re,
        datos_in,
        datos_aj,
        datos_pt,
        df_quipus,
    ]

    for df in frames:
        if df.empty:
            continue
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        df["flor"] = df["flor"].astype(str).str.strip().replace(FLOWER_MAP)
        df["variedad"] = _normalize_text(df["variedad"])
        df["color"] = _normalize_text(df["color"])
        df["tipo"] = df["tipo"].astype(str)
        df["tallos"] = pd.to_numeric(df["tallos"], errors="coerce").fillna(0)

    df_all = pd.concat(frames, axis=0, ignore_index=True)
    df_all["fecha"] = pd.to_datetime(df_all["fecha"], errors="coerce")
    df = pd.merge(df_all, df_dates, on="fecha", how="left")
    df = df[df["año"].notna()].copy()
    df["aass"] = safe_int_series(df["aass"]).astype(int)
    df["año"] = safe_int_series(df["año"]).astype(int)
    df["mes"] = safe_int_series(df["mes"]).astype(int)
    df["semana"] = safe_int_series(df["semana"]).astype(int)
    df = df[df["año"] > 2022].copy()
    df["ntipo"] = df["tipo"] + df["año"].astype(str)

    output_csv = Path(normalize_path(settings.COMPARE_TIKA_OUTPUT_PATH))
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    output_excel = Path(normalize_path(settings.COMPARE_TIKA_OUTPUT_EXCEL_PATH))
    output_excel.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(output_excel, index=False)

    # Se reemplaza en cada corrida, igual que el CSV/Excel.
    dataframe_to_sql(df, "tika_compara_produccion", if_exists="replace")

    return str(output_csv)
