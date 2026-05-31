"""Funciones compartidas entre generadores ETL."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from dbfread import DBF
from sqlalchemy import create_engine

from app.core.db import db_connection
from app.core.settings import settings
from app.services.dbf_reader import normalize_path
from app.services.date_service import (
    ajustar_a_jueves as _ajustar_a_jueves,
    create_date_table as _create_date_table,
    create_month_period_table as _create_month_period_table,
    get_bogota_now,
)


# ---------------------------------------------------------------------------
# Lectura de archivos DBF
# ---------------------------------------------------------------------------

def read_dbf(path: str) -> pd.DataFrame:
    """Lee un DBF probando múltiples encodings. Retorna DataFrame con columnas en minúscula."""
    normalized_path = normalize_path(path)
    if not Path(normalized_path).exists():
        raise FileNotFoundError(f"No existe el archivo DBF: {normalized_path}")

    last_error: Exception | None = None
    for encoding in settings.DBF_ENCODINGS:
        try:
            table = DBF(normalized_path, encoding=encoding)
            rows = [dict(record) for record in table]
            if not rows:
                return pd.DataFrame()
            df = pd.DataFrame(rows)
            df.columns = [str(col).strip().lower() for col in df.columns]
            return df
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    raise RuntimeError(f"No se pudo leer DBF {normalized_path}: {last_error}")


def read_many_dbf(base_dir: str, filenames: Iterable[str]) -> pd.DataFrame:
    """Lee y concatena varios DBF de un mismo directorio, omitiendo los que no existan."""
    frames: list[pd.DataFrame] = []
    normalized_base = normalize_path(base_dir).rstrip("\\/")

    for filename in filenames:
        full_path = f"{normalized_base}\\{filename}"
        if not Path(full_path).exists():
            continue
        frame = read_dbf(full_path)
        if not frame.empty:
            frames.append(frame)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Utilidades de datos
# ---------------------------------------------------------------------------

def safe_int_series(series: pd.Series) -> pd.Series:
    """Convierte una serie a numérico con fallback a 0."""
    return pd.to_numeric(series, errors="coerce").fillna(0)


def normalize_finca_series(series: pd.Series) -> pd.Series:
    """Normaliza finca a codigo string de 3 digitos (001/002/...)."""
    mapped = series.astype(str).str.strip().str.upper()

    mapped = mapped.str.replace(r"^FINCA\s+", "", regex=True)

    name_map = {
        "INVERPALMAS": "001",
        "PALERMO": "002",
    }
    mapped = mapped.replace(name_map)

    numeric = pd.to_numeric(mapped, errors="coerce")
    out = mapped.copy()
    is_num = numeric.notna()
    out.loc[is_num] = numeric.loc[is_num].astype(int).astype(str).str.zfill(3)

    return out


def validate_columns(df: pd.DataFrame, required: set[str], source_name: str) -> None:
    """Lanza ValueError si faltan columnas requeridas en el DataFrame."""
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Faltan columnas en {source_name}: " + ", ".join(sorted(missing))
        )


# ---------------------------------------------------------------------------
# Fechas
# ---------------------------------------------------------------------------

def ajustar_a_jueves(fecha: pd.Timestamp) -> pd.Timestamp:
    """Ajusta la fecha al jueves de la misma semana ISO."""
    return _ajustar_a_jueves(fecha)


def create_date_table(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Genera tabla de fechas con semana ISO, año/mes asignados por el jueves
    de cada semana, aass, aaaass y columnas auxiliares.

    Columnas devueltas:
    fecha, año, mes, semana, aass, dia_semana, lunes, dia, ndia_semana, aaaass
    """
    return _create_date_table(start_date=start_date, end_date=end_date)


def create_month_period_table(date_table: pd.DataFrame) -> pd.DataFrame:
    """Genera tabla de periodos mensuales (último jueves de cada mes)."""
    return _create_month_period_table(date_table)


def default_previous_year_week_range() -> dict[str, str]:
    """Retorna el rango por defecto: lunes de la semana 1 del año anterior a domingo de la semana pasada."""
    now = get_bogota_now()
    today = pd.Timestamp(now.date()).normalize()
    previous_year = today.year - 1
    fecha_inicio = pd.Timestamp(datetime.fromisocalendar(previous_year, 1, 1)).normalize()
    lunes_semana_actual = today - pd.Timedelta(days=today.weekday())
    fecha_fin = (lunes_semana_actual - pd.Timedelta(days=1)).normalize()
    return {
        "fecha_inicio": fecha_inicio.strftime("%Y-%m-%d"),
        "fecha_fin": fecha_fin.strftime("%Y-%m-%d"),
    }


def resolve_date_range_params(params: dict[str, Any] | None = None) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Resuelve fecha_inicio/fecha_fin usando defaults semanales y overrides explícitos."""
    defaults = default_previous_year_week_range()
    raw_inicio = (params or {}).get("fecha_inicio", defaults["fecha_inicio"])
    raw_fin = (params or {}).get("fecha_fin", defaults["fecha_fin"])

    try:
        fecha_inicio = pd.to_datetime(raw_inicio, errors="raise").normalize()
        fecha_fin = pd.to_datetime(raw_fin, errors="raise").normalize()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Las fechas deben tener formato valido (YYYY-MM-DD).") from exc

    if fecha_inicio > fecha_fin:
        raise ValueError("fecha_inicio no puede ser mayor que fecha_fin.")

    return fecha_inicio, fecha_fin


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------

def _get_engine():
    """Crea un engine SQLAlchemy a partir de la configuración de settings."""
    url = (
        f"mysql+pymysql://{settings.DB_USER}:{settings.DB_PASSWORD}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    )
    return create_engine(url)


def dataframe_to_sql(df: pd.DataFrame, table_name: str, if_exists: str = "replace") -> None:
    """Escribe un DataFrame completo a una tabla MySQL."""
    engine = _get_engine()
    df.to_sql(table_name, engine, index=False, if_exists=if_exists)


def execute_query(sql: str):
    """Ejecuta una consulta SQL. Retorna filas para SELECT, None para DML."""
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql)
        if sql.strip().upper().startswith("SELECT"):
            rows = cursor.fetchall()
            cursor.close()
            return rows
        connection.commit()
        cursor.close()
        return None


def delete_data_by_year(table_name: str, year: int) -> None:
    """Elimina registros de una tabla donde YEAR(fecha) = year."""
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "DELETE FROM `%s` WHERE YEAR(fecha) = %%s" % table_name,
            (year,),
        )
        connection.commit()
        cursor.close()


def create_view(view_name: str, sql_query: str) -> None:
    """Crea o reemplaza una vista en la base de datos."""
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(f"CREATE OR REPLACE VIEW `{view_name}` AS {sql_query}")
        connection.commit()
        cursor.close()

class CSVReader:
    """
    A class for reading and preprocessing CSV files.
    
    Attributes:
        file (str): Path to the CSV file.
    """
    
    def __init__(self, file):
        """
        Initialize the CSVReader with a file path.
        
        Args:
            file (str): Path to the CSV file.
        """
        self.file = file
        self._df = None  # Internal cache for the DataFrame
    
    def read(self, **kwargs):
        """
        Read the CSV file into a pandas DataFrame.
        
        Args:
            **kwargs: Additional arguments to pass to pd.read_csv()
            
        Returns:
            pandas.DataFrame: The loaded DataFrame.
        """
        default_kwargs = {
            'thousands': ',',
            'encoding': 'utf-8',
            'na_values': ['', 'NA', 'N/A', 'NaN', 'null'],
            'low_memory': False,  # Importante para evitar problemas de inferencia
        }
        
        # Solo especificar dtype para columnas que no son numéricas
        # Dejar que Pandas infiera las numéricas como float
        default_kwargs.update(kwargs)
        
        self._df = pd.read_csv(self.file, **default_kwargs)
        return self._df
    
    def clean_columns(self):
        """
        Clean the column names by converting to lowercase and replacing spaces with underscores.
        
        Returns:
            pandas.DataFrame: The DataFrame with cleaned column names.
        """
        if self._df is None:
            self.read()
            
        self._df.columns = (
            self._df.columns
            .str.lower()
            .str.replace(' ', '_')
            .str.replace('[^a-z0-9_]', '', regex=True)
        )
        return self._df
    
#proyecciones de Tika
def pico(edad):
    if pd.isna(edad):
        return np.nan
    elif edad >=16 and edad<=35:
        return int(1)
    elif edad >=36 and edad<=70:
        return int(2)
    elif edad>120:
        return np.nan
    else:
        return int(3)