"""Servicios de calendario para ETL."""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta

import pandas as pd

from app.core.db import db_connection
from app.core.settings import settings


def ajustar_a_jueves(fecha: pd.Timestamp) -> pd.Timestamp:
    """Ajusta una fecha al jueves de su semana ISO."""
    if pd.isnull(fecha):
        return fecha
    dia_semana = fecha.weekday()  # 0=lunes, 6=domingo
    if dia_semana <= 3:
        return fecha + pd.Timedelta(days=3 - dia_semana)
    return fecha - pd.Timedelta(days=dia_semana - 3)


def yyww_to_date(yyww: int | str) -> pd.Timestamp:
    """Convierte YYWW a la fecha del jueves de esa semana ISO."""
    token = str(yyww).strip()
    if len(token) != 4 or not token.isdigit():
        raise ValueError(f"Valor YYWW invalido: '{yyww}'.")
    year = 2000 + int(token[:2])
    week = int(token[2:])
    return pd.Timestamp(datetime.fromisocalendar(year, week, 4))


def date_to_yyww(value: date | datetime | pd.Timestamp) -> int:
    """Convierte fecha al identificador ISO YYWW."""
    ts = pd.Timestamp(value)
    iso = ts.isocalendar()
    return int(f"{iso.year % 100:02d}{iso.week:02d}")


def get_current_iso_week() -> int:
    """Retorna la semana ISO actual en formato YYWW."""
    return date_to_yyww(pd.Timestamp.today())


def get_bogota_now() -> datetime:
    """Retorna la hora actual en zona horaria de Bogotá."""
    # Obtener la zona horaria configurada (América/Bogotá = UTC-5)
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(settings.TIMEZONE)
    except (ImportError, Exception):
        # Fallback para Python < 3.9 o si zoneinfo no está disponible
        # Bogotá siempre está en UTC-5 (sin horario de verano)
        tz = timezone(timedelta(hours=-5))
    
    return datetime.now(tz)


def create_date_table(start_date: str, end_date: str) -> pd.DataFrame:
    """Genera una tabla de fechas con atributos de calendario ISO."""
    date_range = pd.date_range(start=start_date, end=end_date)
    df = pd.DataFrame(date_range, columns=["fecha"])

    iso = df["fecha"].dt.isocalendar()
    df["dia_semana"] = iso.day.astype(int)
    df["semana"] = iso.week.astype(int)

    df["lunes"] = df["fecha"] - pd.to_timedelta(df["dia_semana"] - 1, unit="D")
    jueves = df["lunes"] + pd.Timedelta(days=3)

    df["año"] = jueves.dt.year
    df["mes"] = jueves.dt.month

    df["aass"] = (
        jueves.dt.strftime("%y") + df["semana"].astype(str).str.zfill(2)
    ).astype(int)

    df["ndia_semana"] = df["fecha"].dt.dayofweek + 1

    try:
        df["dia"] = df["fecha"].dt.day_name(locale="es_ES")
    except Exception:  # noqa: BLE001
        df["dia"] = df["fecha"].dt.day_name()

    df["aaaass"] = (
        jueves.dt.year.astype(str) + jueves.dt.month.astype(str).str.zfill(2)
    ).astype(int)

    column_order = [
        "fecha",
        "año",
        "mes",
        "semana",
        "aass",
        "dia_semana",
        "lunes",
        "dia",
        "ndia_semana",
        "aaaass",
    ]
    return df[column_order]


def create_month_period_table(date_table: pd.DataFrame) -> pd.DataFrame:
    """Calcula periodo mensual usando ultimo jueves de cada mes."""
    df_month_week = (
        date_table.loc[date_table["dia_semana"] == 4, ["año", "mes", "fecha"]]
        .groupby(["año", "mes"], as_index=False)["fecha"]
        .max()
    )
    df_month_week["periodo"] = (
        df_month_week["año"].astype(str).str.zfill(4)
        + df_month_week["mes"].astype(str).str.zfill(2)
    )
    return df_month_week


def load_dates_from_db(start_date: str, end_date: str) -> pd.DataFrame:
    """Lee la tabla dates para un rango y retorna columnas normalizadas."""
    with db_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT fecha, año, mes, semana, aass, dia_semana
            FROM dates
            WHERE fecha BETWEEN %s AND %s
            ORDER BY fecha
            """,
            (start_date, end_date),
        )
        rows = cursor.fetchall()
        cursor.close()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["fecha"] = pd.to_datetime(df["fecha"]) 
    df["semana"] = pd.to_numeric(df["semana"], errors="coerce").fillna(0).astype(int)
    df["año"] = pd.to_numeric(df["año"], errors="coerce").fillna(0).astype(int)
    df["mes"] = pd.to_numeric(df["mes"], errors="coerce").fillna(0).astype(int)
    if "aass" in df.columns:
        df["aass"] = pd.to_numeric(df["aass"], errors="coerce").fillna(0).astype(int)
    if "dia_semana" in df.columns:
        df["dia_semana"] = pd.to_numeric(df["dia_semana"], errors="coerce").fillna(0).astype(int)

    df["lunes"] = df["fecha"] - pd.to_timedelta(df["fecha"].dt.dayofweek, unit="D")
    df["ndia_semana"] = df["fecha"].dt.dayofweek + 1
    try:
        df["dia"] = df["fecha"].dt.day_name(locale="es_ES")
    except Exception:  # noqa: BLE001
        df["dia"] = df["fecha"].dt.day_name()

    df["aaaass"] = (
        df["año"].astype(str).str.zfill(4) + df["mes"].astype(str).str.zfill(2)
    ).astype(int)

    column_order = [
        "fecha",
        "año",
        "mes",
        "semana",
        "aass",
        "dia_semana",
        "lunes",
        "dia",
        "ndia_semana",
        "aaaass",
    ]
    for column in column_order:
        if column not in df.columns:
            df[column] = pd.NA
    return df[column_order]


def get_dates_dimension(start_date: str, end_date: str) -> pd.DataFrame:
    """Devuelve calendario desde BD y usa fallback local si falla."""
    try:
        db_dates = load_dates_from_db(start_date=start_date, end_date=end_date)
        if not db_dates.empty:
            return db_dates
    except Exception:  # noqa: BLE001
        pass
    return create_date_table(start_date=start_date, end_date=end_date)
