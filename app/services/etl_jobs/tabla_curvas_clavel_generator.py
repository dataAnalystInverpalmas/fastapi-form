"""Genera tabla de curvas clavel desde DBF Curvas_por_Tiqueteado_EC.dbf."""
from __future__ import annotations

import pandas as pd

from app.core.settings import settings
from app.services.etl.helpers import (
    ajustar_a_jueves,
    dataframe_to_sql,
    read_dbf,
    validate_columns,
)


def generate_tabla_curvas_clavel() -> str:
    """
    Lee DBF Curvas_por_Tiqueteado_EC.dbf, procesa y carga datos en tabla
    ld_curvas_clavel. También exporta a CSV.
    
    Pasos:
    1. Leer archivo DBF
    2. Seleccionar columnas relevantes
    3. Limpiar datos (ajustar fechas, filtrar variedades)
    4. Cargar a MySQL en tabla ld_curvas_clavel
    5. Exportar a CSV
    """
    # Leer datos
    df = read_dbf(settings.TABLA_CURVAS_CLAVEL_DBF_PATH)
    if df.empty:
        raise RuntimeError("El archivo Curvas_por_Tiqueteado_EC.dbf no contiene datos.")

    # Validar columnas requeridas
    required_cols = {"lunes", "finca", "cflor", "bloque", "variedad", "nvariedad", 
                     "cosecha", "edad", "f_m", "provee", "matas", "corte"}
    validate_columns(df, required_cols, "Curvas_por_Tiqueteado_EC.dbf")

    # Seleccionar columnas de interés
    df_processed = df[
        ["lunes", "finca", "cflor", "bloque", "variedad", "nvariedad", 
         "cosecha", "edad", "f_m", "provee", "matas", "corte"]
    ].copy()

    # Procesar fechas: convertir a datetime y ajustar al jueves
    df_processed["lunes"] = pd.to_datetime(df_processed["lunes"], errors="coerce")
    df_processed["lunes"] = df_processed["lunes"].apply(ajustar_a_jueves)

    # Filtrar variedad excluida (según notebook)
    variedad_excluida = settings.TABLA_CURVAS_CLAVEL_VARIEDAD_EXCLUIDA
    df_processed = df_processed.query("variedad != @variedad_excluida").copy()

    if df_processed.empty:
        raise RuntimeError("Después de aplicar filtros, no quedan datos para procesar.")

    # Cargar a MySQL tabla ld_curvas_clavel
    dataframe_to_sql(df_processed, "ld_curvas_clavel", if_exists="replace")

    # Exportar a CSV
    df_processed["lunes"] = pd.to_datetime(df_processed["lunes"])
    df_processed.to_csv(settings.TABLA_CURVAS_CLAVEL_OUTPUT_CSV, index=False)

    return f"mysql:informes.ld_curvas_clavel | csv:{settings.TABLA_CURVAS_CLAVEL_OUTPUT_CSV}"
