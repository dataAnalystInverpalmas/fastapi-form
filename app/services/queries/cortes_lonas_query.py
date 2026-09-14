from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.db import db_connection
from app.core.settings import settings
from app.services.utils.dbf_reader import normalize_path


def _table_columns(table_name: str) -> set[str]:
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            """,
            (table_name,),
        )
        cols = {str(row[0]).lower() for row in cursor.fetchall()}
        cursor.close()
    return cols


def exporta_cortes_lonas_excel(fecha_inicio: str, fecha_fin: str) -> str:
    try:
        ini = pd.to_datetime(fecha_inicio, errors="raise").normalize()
        fin = pd.to_datetime(fecha_fin, errors="raise").normalize()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Fechas invalidas. Usa formato YYYY-MM-DD.") from exc

    if ini > fin:
        raise ValueError("fecha_inicio no puede ser mayor que fecha_fin.")

    cols = _table_columns("ld_lonas")
    if not cols:
        raise RuntimeError("La tabla ld_lonas no existe o no tiene columnas.")

    tallos_col = "tallos" if "tallos" in cols else "lonas"
    fecha_siembra_col = "fecha_siembra" if "fecha_siembra" in cols else "fsiemb"

    flores_sql = ", ".join(f"'{flor}'" for flor in settings.CORTES_LONAS_FLOR_FILTER)

    joins_extra = ""
    where_flor = ""
    if "flor" in cols:
        where_flor = f"AND l.flor IN ({flores_sql})"
    else:
        # Fallback para esquema antiguo: derivar flor desde ld_variedades por nombre de variedad.
        joins_extra = """
        LEFT JOIN ld_variedades AS v
            ON TRIM(v.nombre) = TRIM(l.variedad)
        """
        where_flor = f"AND v.codflor IN ({flores_sql})"

    sql = f"""
        SELECT
            REPLACE(l.variedad, ' ', '_') AS variedad,
            l.finca,
            l.bloque,
            d1.aass AS semana,
            d2.aass AS semana_siembra,
            SUM(COALESCE(l.{tallos_col}, 0)) AS cantidad
        FROM ld_lonas AS l
        LEFT JOIN dates AS d1
            ON d1.fecha = DATE(l.fecha)
        LEFT JOIN dates AS d2
            ON d2.fecha = DATE(l.{fecha_siembra_col})
        {joins_extra}
        WHERE DATE(l.fecha) BETWEEN %s AND %s
          {where_flor}
        GROUP BY l.variedad, l.finca, l.bloque, d1.aass, d2.aass
        ORDER BY l.variedad, l.finca, l.bloque, d1.aass
    """

    with db_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(sql, (ini.date(), fin.date()))
        rows = cursor.fetchall()
        cursor.close()

    df = pd.DataFrame(rows, columns=["variedad", "finca", "bloque", "semana", "semana_siembra", "cantidad"])

    finca_map: dict = {}
    for codigo, nombre in settings.CORTES_LONAS_FINCA_MAP.items():
        finca_map[codigo] = nombre
        finca_map[codigo.lstrip("0") or "0"] = nombre
        finca_map[int(codigo)] = nombre
    if "finca" in df.columns:
        df["finca"] = df["finca"].map(lambda x: finca_map.get(x, finca_map.get(str(x).strip(), x)))

    output_dir = Path(normalize_path(settings.EXCEL_OUTPUT_DIR))
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"processed_cortes_ExportaCortes_{ini.strftime('%Y%m%d')}_{fin.strftime('%Y%m%d')}.xlsx"
    output_path = output_dir / filename

    df.to_excel(output_path, index=False, sheet_name="cortes")
    return str(output_path)


def generate_cortes_lonas(params: dict | None = None) -> str:
    params = params or {}
    output_path = exporta_cortes_lonas_excel(
        fecha_inicio=params.get("fecha_inicio"),
        fecha_fin=params.get("fecha_fin"),
    )
    return f"xlsx:{output_path}"