from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from app.core.settings import settings
from app.services.utils.date_service import ajustar_a_jueves
from app.services.utils.dbf_reader import normalize_path
from app.services.etl.helpers import execute_query, read_dbf, safe_int_series, validate_columns


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

FLOR_MAP: dict[str, str] = settings.PEDIDOS_SURTIDO_FLOR_MAP
COLOR_REPLACEMENTS: dict[str, str] = settings.PEDIDOS_SURTIDO_COLOR_REPLACEMENTS

REQUIRED_COLUMNS: set[str] = {
    "nomcli", "despacho", "nomzona", "nompais", "nomciudad",
    "nomvend", "nomagencia", "nomaero", "flor", "nomvarieda",
    "nomgcolor", "grado", "surtido", "tot_tallos", "tcant",
}


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


def _load_dates_jueves() -> pd.DataFrame:
    """Retorna tabla de fechas jueves (dia_semana=4) con aass, año, semana."""
    rows = execute_query(
        "SELECT aass, fecha, año, semana FROM dates WHERE dia_semana = 4"
    ) or []
    df = pd.DataFrame(rows, columns=["aass", "fecha", "año", "semana"])
    if df.empty:
        raise RuntimeError("No se encontraron fechas jueves en la tabla dates.")
    df["aass"] = safe_int_series(df["aass"]).astype(int)
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


def _last_52_week_dates(df_dates: pd.DataFrame, max_fecha: pd.Timestamp) -> pd.DataFrame:
    """Retorna las ultimas 52 semanas jueves disponibles hasta la fecha maxima."""
    df_window = (
        df_dates[df_dates["fecha"] <= max_fecha]
        .sort_values("fecha")
        .drop_duplicates(subset=["fecha"], keep="last")
        .tail(settings.PEDIDOS_SURTIDO_VENTANA_SEMANAS)
        .copy()
    )
    if df_window.empty:
        raise RuntimeError(
            f"No fue posible determinar las ultimas {settings.PEDIDOS_SURTIDO_VENTANA_SEMANAS} semanas de despachos."
        )
    return df_window


def _build_projected_aass(week_series: pd.Series, target_year: int) -> pd.Series:
    """Construye YYWW usando el año destino y el numero ISO de semana."""
    prefix = f"{target_year % 100:02d}"
    weeks = safe_int_series(week_series).astype(int).astype(str).str.zfill(2)
    return (prefix + weeks).astype(int)


# ---------------------------------------------------------------------------
# runner principal
# ---------------------------------------------------------------------------

def generate_pedidos_surtidos(params: dict[str, Any] | None = None) -> str:
    """
    Lee PEDIDOS_surtido.dbf y genera el archivo de despachos (ventas ultimo año.xlsx)
    para ser consumido por el job 'compare_tika_produccion_despachos'.

    Params opcionales:
      proyeccion_anio (int) – año al que se proyectan los despachos históricos.
                               0 = sin proyección. Default: settings.PEDIDOS_SURTIDO_PROYECCION_ANIO.
    """
    params = params or {}
    proyeccion_anio = int(
        params.get("proyeccion_anio") or settings.PEDIDOS_SURTIDO_PROYECCION_ANIO
    )

    # 1. Fechas jueves desde la BD
    df_dates = _load_dates_jueves()

    # 2. Leer DBF
    df_raw = read_dbf(settings.PEDIDOS_SURTIDO_DBF_PATH)
    if df_raw.empty:
        raise RuntimeError("El archivo PEDIDOS_surtido.dbf no contiene datos.")

    df_raw = _normalize_columns(df_raw)
    validate_columns(df_raw, REQUIRED_COLUMNS, "PEDIDOS_surtido.dbf")

    # 3. Seleccionar columnas y ajustar fecha
    df_q = df_raw[list(REQUIRED_COLUMNS)].copy()
    df_q["despacho"] = pd.to_datetime(df_q["despacho"], errors="coerce")
    df_q["despacho"] = df_q["despacho"].apply(ajustar_a_jueves)

    # 4. Filtrar flores válidas
    df_q = df_q[df_q["flor"].isin(settings.PEDIDOS_SURTIDO_FLOR_FILTER)].copy()

    # 5. Unir con tabla de fechas para obtener aass, año, semana
    df_q = pd.merge(
        df_q,
        df_dates.rename(columns={"fecha": "despacho"}),
        on="despacho",
        how="left",
    )

    # 6. Conservar solo las ultimas 52 semanas disponibles por fecha jueves
    max_despacho = df_q["despacho"].max()
    if pd.isna(max_despacho):
        raise RuntimeError("No se encontraron fechas de despacho validas en PEDIDOS_surtido.dbf.")

    df_window = _last_52_week_dates(df_dates, max_despacho)
    df_q = df_q[df_q["despacho"].isin(df_window["fecha"])].copy()

    # 7. Construir df_venta (solo CLA y CM0) y proyectar el año desde el input
    df_venta = df_q[["aass", "semana", "nomvarieda", "nomgcolor", "flor", "tot_tallos"]].copy()
    df_venta = df_venta[df_venta["flor"].isin(settings.PEDIDOS_SURTIDO_FLOR_FILTER)].copy()

    # 8. Normalizar texto
    df_venta["nomvarieda"] = df_venta["nomvarieda"].str.replace(" ", "_", regex=False)
    df_venta["nomgcolor"] = (
        df_venta["nomgcolor"].astype(str).str.upper().str.replace(" ", "_", regex=False)
    )
    df_venta["nflor"] = df_venta["flor"].map(FLOR_MAP)
    df_venta["tot_tallos"] = pd.to_numeric(df_venta["tot_tallos"], errors="coerce").fillna(0)
    if proyeccion_anio > 0:
        df_venta["aass"] = _build_projected_aass(df_venta["semana"], proyeccion_anio)

    # 9. Agrupar por semana / color / flor / variedad
    df_grouped = (
        df_venta.dropna(subset=["aass"])
        .groupby(["aass", "nomgcolor", "nflor", "nomvarieda"], dropna=False)["tot_tallos"]
        .sum()
        .reset_index()
        .rename(columns={
            "nomgcolor": "color",
            "nflor": "flor",
            "tot_tallos": "tallos",
            "nomvarieda": "variedad",
        })
    )
    df_grouped["aass"] = df_grouped["aass"].astype(int)

    # 10. Mantener solo el calendario proyectado solicitado
    df_grouped["tipo"] = "despachos"

    # 11. Unir con fechas para obtener la fecha del calendario proyectado
    df_out = pd.merge(
        df_grouped,
        df_dates[["aass", "fecha"]],
        on="aass",
        how="left",
    ).drop(columns=["aass"])
    if df_out["fecha"].isna().any():
        raise RuntimeError("Algunas semanas proyectadas no existen en la tabla dates para el año solicitado.")

    # 12. Reemplazos de color
    df_out["color"] = df_out["color"].replace(COLOR_REPLACEMENTS)

    # 13. Consolidar claves finales despues de normalizar color
    df_out = (
        df_out.groupby(["fecha", "flor", "variedad", "color", "tipo"], dropna=False)["tallos"]
        .sum()
        .reset_index()
    )

    # 14. Columnas finales
    df_out = df_out[["fecha", "flor", "variedad", "color", "tallos", "tipo"]].copy()

    # 15. Guardar Excel
    output_path = Path(normalize_path(settings.COMPARE_TIKA_DESPACHOS_PATH))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_excel(output_path, index=False)

    return str(output_path)
