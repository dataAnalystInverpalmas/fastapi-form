"""Build and export the Excel report."""
from __future__ import annotations

import os
from typing import Sequence, Tuple

import pandas as pd

from app.core.db import db_connection
from app.core.settings import settings

SELECT_QUERY = """
SELECT
    p.finca,
    p.bloque,
    s.cod_temporada AS cosecha,
    p.tipo_siembra,
    p.variedad,
    p.fecha_siembra,
    COALESCE(pr.pico, v.ciclo) AS ciclo,
    s.fecha_pico,
    SUM(p.plantas) AS plantas
FROM
    plane AS p
        LEFT JOIN
    seasons AS s ON s.nombre = p.temporada
        INNER JOIN
    varieties AS v ON v.nombre = p.variedad
        LEFT JOIN
    (
        SELECT
            variedad, temporada_obj, pico
        FROM
            program
        WHERE estado=1
        GROUP BY 1, 2, 3
    ) AS pr ON pr.variedad = p.variedad
        AND pr.temporada_obj = s.nombre
WHERE
    p.plantas > 0
GROUP BY p.finca, p.bloque, s.cod_temporada, p.tipo_siembra, p.variedad, p.fecha_siembra
"""

SELECT_QUERY1 = """
SELECT
    a.variedad,
    a.finca,
    a.tipo,
    a.aplicar,
    aa.calc_conciclo AS calculo,
    a.valor
FROM
    arrangements AS a
        LEFT JOIN
    arrangement AS aa ON aa.tipo = a.tipo
        AND aa.aplicar = a.aplicar
"""

SELECT_QUERY2 = "SELECT aass, fecha FROM dates"


ResultSet = Sequence[Tuple]


def fetch_results() -> Tuple[ResultSet, ResultSet, ResultSet]:
    with db_connection() as connection:
        if not connection.is_connected():
            raise RuntimeError("No se pudo conectar a la base de datos.")
        cursor = connection.cursor()
        cursor.execute(SELECT_QUERY)
        resultados = cursor.fetchall()
        cursor.execute(SELECT_QUERY1)
        resultados1 = cursor.fetchall()
        cursor.execute(SELECT_QUERY2)
        resultados2 = cursor.fetchall()
        cursor.close()
    return resultados, resultados1, resultados2


def _calculate_date(row: pd.Series) -> pd.Timestamp:
    calculo = row["calculo"]
    if calculo in [0, 3, 4, 5, 6]:
        return row["fecha"] + pd.DateOffset(days=row["valor"])
    if calculo in [2]:
        return row["fecha_pico"] + pd.DateOffset(days=row["valor"]) + pd.DateOffset(weeks=row["ciclo"])
    if calculo in [7]:
        return row["fecha_pico"] + pd.DateOffset(days=row["valor"])
    return row["fecha"]


def build_output_dataframe(
    resultados: ResultSet,
    resultados1: ResultSet,
    resultados2: ResultSet,
) -> pd.DataFrame:
    df = pd.DataFrame(
        resultados,
        columns=[
            "finca",
            "bloque",
            "cosecha",
            "tipo_siembra",
            "variedad",
            "fecha_siembra",
            "ciclo",
            "fecha_pico",
            "plantas",
        ],
    )
    df1 = pd.DataFrame(resultados1, columns=["variedad", "finca", "tipo", "aplicar", "calculo", "valor"])
    df_d = pd.DataFrame(resultados2, columns=["aaaass", "fecha"])
    df_d["fecha"] = pd.to_datetime(df_d["fecha"])

    df = df[pd.notna(df["cosecha"])]
    df["fecha_siembra"] = pd.to_datetime(df["fecha_siembra"])
    df["fecha_pico"] = pd.to_datetime(df["fecha_pico"])

    df["fecha"] = df.apply(
        lambda row: row["fecha_siembra"] + pd.DateOffset(weeks=row["ciclo"])
        if row["tipo_siembra"] in ["ADICIONAL", "REEMPLAZO"]
        else row["fecha_pico"] - pd.DateOffset(weeks=row["ciclo"]),
        axis=1,
    )
    df = df[["finca", "bloque", "cosecha", "variedad", "ciclo", "plantas", "fecha"]]
    df["fecha_pico"] = df.apply(lambda row: row["fecha"] + pd.DateOffset(weeks=row["ciclo"]), axis=1)

    dframe = pd.merge(df, df1, on=["finca", "variedad"], how="left")
    df_a = dframe.copy()

    df_a["fecha_aplica"] = df_a.apply(_calculate_date, axis=1)
    df_d.rename({"fecha": "fecha_aplica"}, axis=1, inplace=True)
    df_out = pd.merge(df_a, df_d, on="fecha_aplica", how="inner")
    return df_out


def write_excel(
    df_out: pd.DataFrame,
    output_dir: str | None = None,
    filename: str | None = None,
) -> str:
    final_output_dir = output_dir or settings.EXCEL_OUTPUT_DIR
    final_filename = filename or settings.EXCEL_FILENAME
    os.makedirs(final_output_dir, exist_ok=True)
    output_path = os.path.join(final_output_dir, final_filename)
    df_out.to_excel(output_path, index=False)
    return output_path


def generate_excel_file(
    output_dir: str | None = None,
    filename: str | None = None,
) -> str:
    resultados, resultados1, resultados2 = fetch_results()
    df_out = build_output_dataframe(resultados, resultados1, resultados2)
    final_filename = filename or settings.EXCEL_FILENAME
    return write_excel(df_out, output_dir=output_dir, filename=final_filename)
