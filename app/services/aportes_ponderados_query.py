from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.db import db_connection
from app.core.settings import settings
from app.services.dbf_reader import normalize_path

_SQL_APORTES_PONDERADOS = """
    WITH base_lonas AS (
        SELECT
            LPAD(TRIM(CAST(l.finca AS CHAR)), 3, '0') AS finca,
            TRIM(COALESCE(l.flor, '')) AS flor,
            d.aass AS aass,
            SUM(COALESCE(l.tallos, 0)) AS tallos
        FROM ld_lonas AS l
        LEFT JOIN dates AS d
            ON d.fecha = DATE(l.fecha)
        WHERE DATE(l.fecha) BETWEEN %s AND %s
          AND LPAD(TRIM(CAST(l.finca AS CHAR)), 3, '0') IN ('001', '002')
        GROUP BY LPAD(TRIM(CAST(l.finca AS CHAR)), 3, '0'), TRIM(COALESCE(l.flor, '')), d.aass
    ),
    cultivo_totales AS (
        SELECT
            LPAD(TRIM(CAST(n.finca AS CHAR)), 3, '0') AS finca,
            TRIM(COALESCE(n.flor, '')) AS flor,
            d.aass AS aass,
            SUM(COALESCE(n.muestra, 0)) AS tallos_fito
        FROM ld_nacional AS n
        LEFT JOIN dates AS d
            ON d.fecha = DATE(n.fecha)
        WHERE DATE(n.fecha) BETWEEN %s AND %s
          AND UPPER(TRIM(COALESCE(n.fuente, ''))) = 'CULTIVO'
          AND UPPER(TRIM(COALESCE(n.grado, ''))) = 'NAL'
          AND LPAD(TRIM(CAST(n.finca AS CHAR)), 3, '0') IN ('001', '002')
        GROUP BY LPAD(TRIM(CAST(n.finca AS CHAR)), 3, '0'), TRIM(COALESCE(n.flor, '')), d.aass
    ),
    dirigida_totales AS (
        SELECT
            LPAD(TRIM(CAST(n.finca AS CHAR)), 3, '0') AS finca,
            TRIM(COALESCE(n.flor, '')) AS flor,
            d.aass AS aass,
            SUM(COALESCE(n.muestra, 0)) AS tallos_nacional_dirigida
        FROM ld_nacional AS n
        LEFT JOIN dates AS d
            ON d.fecha = DATE(n.fecha)
        WHERE DATE(n.fecha) BETWEEN %s AND %s
          AND UPPER(TRIM(COALESCE(n.fuente, ''))) = 'DIRIGIDA'
          AND UPPER(TRIM(COALESCE(n.grado, ''))) = 'NAL'
          AND LPAD(TRIM(CAST(n.finca AS CHAR)), 3, '0') IN ('001', '002')
        GROUP BY LPAD(TRIM(CAST(n.finca AS CHAR)), 3, '0'), TRIM(COALESCE(n.flor, '')), d.aass
    ),
    base_porcentajes AS (
        SELECT
            b.finca,
            b.flor,
            b.aass,
            b.tallos,
            COALESCE(c.tallos_fito, 0) AS tallos_fito,
            CASE
                WHEN COALESCE(b.tallos, 0) = 0 THEN 0
                ELSE COALESCE(c.tallos_fito, 0) / b.tallos
            END AS porcentaje_fito,
            COALESCE(d.tallos_nacional_dirigida, 0) AS tallos_nacional_dirigida,
            CASE
                WHEN COALESCE(b.tallos, 0) = 0 THEN 0
                ELSE COALESCE(d.tallos_nacional_dirigida, 0) / b.tallos
            END AS porcentaje_nacional_dirigida
        FROM base_lonas AS b
        LEFT JOIN cultivo_totales AS c
            ON c.finca = b.finca AND c.flor = b.flor AND c.aass = b.aass
        LEFT JOIN dirigida_totales AS d
            ON d.finca = b.finca AND d.flor = b.flor AND d.aass = b.aass
    ),
    cultivo_problema AS (
        SELECT
            LPAD(TRIM(CAST(n.finca AS CHAR)), 3, '0') AS finca,
            TRIM(COALESCE(n.flor, '')) AS flor,
            d.aass AS aass,
            TRIM(COALESCE(n.problema, 'SIN_PROBLEMA')) AS problema,
            SUM(COALESCE(n.tallos, 0)) AS tallos_problema,
            SUM(SUM(COALESCE(n.tallos, 0))) OVER (
                PARTITION BY LPAD(TRIM(CAST(n.finca AS CHAR)), 3, '0'), TRIM(COALESCE(n.flor, '')), d.aass
            ) AS total_tallos_fuente
        FROM ld_nacional AS n
        LEFT JOIN dates AS d
            ON d.fecha = DATE(n.fecha)
        WHERE DATE(n.fecha) BETWEEN %s AND %s
          AND UPPER(TRIM(COALESCE(n.fuente, ''))) = 'CULTIVO'
          AND UPPER(TRIM(COALESCE(n.grado, ''))) = 'NAL'
          AND LPAD(TRIM(CAST(n.finca AS CHAR)), 3, '0') IN ('001', '002')
        GROUP BY
            LPAD(TRIM(CAST(n.finca AS CHAR)), 3, '0'),
            TRIM(COALESCE(n.flor, '')),
            d.aass,
            TRIM(COALESCE(n.problema, 'SIN_PROBLEMA'))
    ),
    dirigida_problema AS (
        SELECT
            LPAD(TRIM(CAST(n.finca AS CHAR)), 3, '0') AS finca,
            TRIM(COALESCE(n.flor, '')) AS flor,
            d.aass AS aass,
            TRIM(COALESCE(n.problema, 'SIN_PROBLEMA')) AS problema,
            SUM(COALESCE(n.tallos, 0)) AS tallos_problema,
            SUM(SUM(COALESCE(n.tallos, 0))) OVER (
                PARTITION BY LPAD(TRIM(CAST(n.finca AS CHAR)), 3, '0'), TRIM(COALESCE(n.flor, '')), d.aass
            ) AS total_tallos_fuente
        FROM ld_nacional AS n
        LEFT JOIN dates AS d
            ON d.fecha = DATE(n.fecha)
        WHERE DATE(n.fecha) BETWEEN %s AND %s
          AND UPPER(TRIM(COALESCE(n.fuente, ''))) = 'DIRIGIDA'
          AND UPPER(TRIM(COALESCE(n.grado, ''))) = 'NAL'
          AND LPAD(TRIM(CAST(n.finca AS CHAR)), 3, '0') IN ('001', '002')
        GROUP BY
            LPAD(TRIM(CAST(n.finca AS CHAR)), 3, '0'),
            TRIM(COALESCE(n.flor, '')),
            d.aass,
            TRIM(COALESCE(n.problema, 'SIN_PROBLEMA'))
    ),
    ponderados AS (
        SELECT
            cp.finca,
            cp.flor,
            cp.aass,
            cp.problema,
            (
                CASE
                    WHEN COALESCE(cp.total_tallos_fuente, 0) = 0 THEN 0
                    ELSE cp.tallos_problema / cp.total_tallos_fuente
                END
            ) * COALESCE(bp.porcentaje_fito, 0) AS aporte_ponderado
        FROM cultivo_problema AS cp
        INNER JOIN base_porcentajes AS bp
            ON bp.finca = cp.finca AND bp.flor = cp.flor AND bp.aass = cp.aass

        UNION ALL

        SELECT
            dp.finca,
            dp.flor,
            dp.aass,
            dp.problema,
            (
                CASE
                    WHEN COALESCE(dp.total_tallos_fuente, 0) = 0 THEN 0
                    ELSE dp.tallos_problema / dp.total_tallos_fuente
                END
            ) * COALESCE(bp.porcentaje_nacional_dirigida, 0) AS aporte_ponderado
        FROM dirigida_problema AS dp
        INNER JOIN base_porcentajes AS bp
            ON bp.finca = dp.finca AND bp.flor = dp.flor AND bp.aass = dp.aass
    ),
    aportes_agrupados AS (
        SELECT
            finca,
            flor,
            aass,
            problema,
            SUM(COALESCE(aporte_ponderado, 0)) AS aporte_ponderado_sum
        FROM ponderados
        GROUP BY finca, flor, aass, problema
    ),
    aporte_total_grupo AS (
        SELECT
            finca,
            flor,
            aass,
            SUM(COALESCE(aporte_ponderado_sum, 0)) AS aporte_total
        FROM aportes_agrupados
        GROUP BY finca, flor, aass
    )
    SELECT
        a.finca,
        a.flor,
        a.aass,
        a.problema,
        CASE
            WHEN COALESCE(g.aporte_total, 0) = 0 THEN 0
            ELSE a.aporte_ponderado_sum / g.aporte_total
        END AS aporte_final
    FROM aportes_agrupados AS a
    INNER JOIN aporte_total_grupo AS g
        ON g.finca = a.finca AND g.flor = a.flor AND g.aass = a.aass
    ORDER BY a.finca, a.flor, a.aass, a.problema
"""


def exporta_aportes_ponderados_problemas_excel(fecha_inicio: str, fecha_fin: str) -> str:
    try:
        ini = pd.to_datetime(fecha_inicio, errors="raise").normalize()
        fin = pd.to_datetime(fecha_fin, errors="raise").normalize()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Fechas invalidas. Usa formato YYYY-MM-DD.") from exc

    if ini > fin:
        raise ValueError("fecha_inicio no puede ser mayor que fecha_fin.")

    params = (
        ini.date(),
        fin.date(),
        ini.date(),
        fin.date(),
        ini.date(),
        fin.date(),
        ini.date(),
        fin.date(),
        ini.date(),
        fin.date(),
    )

    with db_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(_SQL_APORTES_PONDERADOS, params)
        rows = cursor.fetchall()
        cursor.close()

    df = pd.DataFrame(rows, columns=["finca", "flor", "aass", "problema", "aporte_final"])

    output_dir = Path(normalize_path(settings.EXCEL_OUTPUT_DIR))
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"aportes_ponderados_problemas_{ini.strftime('%Y%m%d')}_{fin.strftime('%Y%m%d')}.xlsx"
    output_path = output_dir / filename

    df.to_excel(output_path, index=False, sheet_name="aportes_ponderados")
    return str(output_path)