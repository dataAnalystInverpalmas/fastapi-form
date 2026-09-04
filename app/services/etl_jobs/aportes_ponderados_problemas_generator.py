from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.db import db_connection
from app.core.settings import settings
from app.services.etl.helpers import resolve_date_range_params
from app.services.utils.dbf_reader import normalize_path

_SQL_APORTES_PONDERADOS = """
WITH
-- =====================================
-- PRODUCCION TOTAL (LONAS)
-- =====================================
base_lonas AS (
    SELECT
        LPAD(TRIM(CAST(l.finca AS CHAR)),3,'0') AS finca,
        TRIM(COALESCE(l.flor,'')) AS flor,
        d.aass,
        SUM(COALESCE(l.tallos,0)) AS tallos
    FROM ld_lonas l
    LEFT JOIN dates d
        ON d.fecha = DATE(l.fecha)
    WHERE DATE(l.fecha) BETWEEN %s AND %s
      AND LPAD(TRIM(CAST(l.finca AS CHAR)),3,'0') IN ('001','002')
    GROUP BY 1,2,3

    UNION ALL

    SELECT
        '000' AS finca,
        TRIM(COALESCE(l.flor,'')) AS flor,
        d.aass,
        SUM(COALESCE(l.tallos,0)) AS tallos
    FROM ld_lonas l
    LEFT JOIN dates d
        ON d.fecha = DATE(l.fecha)
    WHERE DATE(l.fecha) BETWEEN %s AND %s
      AND TRIM(COALESCE(l.flor,'')) IN ('CLA','CM0')
    GROUP BY 2,3
),

-- =====================================
-- FITO CULTIVO (ld_nacional)
-- =====================================
cultivo_totales AS (
    SELECT
        LPAD(TRIM(CAST(n.finca AS CHAR)),3,'0') AS finca,
        TRIM(COALESCE(n.flor,'')) AS flor,
        d.aass,
        SUM(COALESCE(n.tallos,0)) AS tallos_fito
    FROM ld_producto_procesado n
    LEFT JOIN dates d
        ON d.fecha = DATE(n.fecha)
    WHERE DATE(n.fecha) BETWEEN %s AND %s
      AND UPPER(TRIM(COALESCE(n.fuente,'')))='Fitosanitario Cultivo'
      AND LPAD(TRIM(CAST(n.finca AS CHAR)),3,'0') IN ('001','002')
    GROUP BY 1,2,3

    UNION ALL

    SELECT
        '000' AS finca,
        TRIM(COALESCE(n.flor,'')) AS flor,
        d.aass,
        SUM(COALESCE(n.tallos,0)) AS tallos_fito
    FROM ld_producto_procesado n
    LEFT JOIN dates d
        ON d.fecha = DATE(n.fecha)
    WHERE DATE(n.fecha) BETWEEN %s AND %s
      AND UPPER(TRIM(COALESCE(n.fuente,'')))='Fitosanitario Cultivo'
      AND TRIM(COALESCE(n.flor,'')) IN ('CLA','CM0')
    GROUP BY 2,3
),

-- =====================================
-- FITO DIRIGIDA (ld_producto_procesado)
-- =====================================
dirigida_totales AS (
    SELECT
        LPAD(TRIM(CAST(p.finca AS CHAR)),3,'0') AS finca,
        TRIM(COALESCE(p.flor,'')) AS flor,
        d.aass,
        SUM(COALESCE(p.tallos, 0)) AS tallos_totales_dirigida,
        SUM(CASE WHEN UPPER(TRIM(COALESCE(p.grado, ''))) = 'NAL' THEN COALESCE(p.tallos, 0) ELSE 0 END) AS tallos_nacional_dirigida
    FROM ld_producto_procesado p
    LEFT JOIN dates d
        ON d.fecha = DATE(p.fecha)
    WHERE DATE(p.fecha) BETWEEN %s AND %s
      AND UPPER(TRIM(COALESCE(p.fuente,'')))='DIRIGIDA'
      AND LPAD(TRIM(CAST(p.finca AS CHAR)),3,'0') IN ('001','002')
    GROUP BY 1,2,3

    UNION ALL

    SELECT
        '000' AS finca,
        TRIM(COALESCE(p.flor,'')) AS flor,
        d.aass,
        SUM(COALESCE(p.tallos, 0)) AS tallos_totales_dirigida,
        SUM(CASE WHEN UPPER(TRIM(COALESCE(p.grado, ''))) = 'NAL' THEN COALESCE(p.tallos, 0) ELSE 0 END) AS tallos_nacional_dirigida
    FROM ld_producto_procesado p
    LEFT JOIN dates d
        ON d.fecha = DATE(p.fecha)
    WHERE DATE(p.fecha) BETWEEN %s AND %s
      AND UPPER(TRIM(COALESCE(p.fuente,'')))='DIRIGIDA'
      AND TRIM(COALESCE(p.flor,'')) IN ('CLA','CM0')
    GROUP BY 2,3
),

-- =====================================
-- PORCENTAJES BASE
-- =====================================
base_porcentajes AS (
    SELECT
        b.finca,
        b.flor,
        b.aass,
        b.tallos,

        COALESCE(c.tallos_fito,0) AS tallos_fito,
        COALESCE(d.tallos_nacional_dirigida,0) AS tallos_nacional_dirigida,

        COALESCE(c.tallos_fito,0)/b.tallos AS pct_fito,
        COALESCE(d.tallos_nacional_dirigida,0)/d.tallos_totales_dirigida AS pct_dirigida,

        CASE
            WHEN (
                COALESCE(c.tallos_fito,0)/b.tallos +
                COALESCE(d.tallos_nacional_dirigida,0)/d.tallos_totales_dirigida
            ) = 0 THEN 0
            ELSE
                (COALESCE(c.tallos_fito,0)/b.tallos) /
                (
                    COALESCE(c.tallos_fito,0)/b.tallos +
                    COALESCE(d.tallos_nacional_dirigida,0)/d.tallos_totales_dirigida
                )
        END AS porcentaje_fito,

        CASE
            WHEN (
                COALESCE(c.tallos_fito,0)/b.tallos +
                COALESCE(d.tallos_nacional_dirigida,0)/d.tallos_totales_dirigida
            ) = 0 THEN 0
            ELSE
                (COALESCE(d.tallos_nacional_dirigida,0)/d.tallos_totales_dirigida) /
                (
                    COALESCE(c.tallos_fito,0)/b.tallos +
                    COALESCE(d.tallos_nacional_dirigida,0)/d.tallos_totales_dirigida
                )
        END AS porcentaje_nacional_dirigida

    FROM base_lonas b
    LEFT JOIN cultivo_totales c
        ON c.finca=b.finca
       AND c.flor=b.flor
       AND c.aass=b.aass
    LEFT JOIN dirigida_totales d
        ON d.finca=b.finca
       AND d.flor=b.flor
       AND d.aass=b.aass
),

-- =====================================
-- PROBLEMAS CULTIVO
-- =====================================
cultivo_problema AS (
    SELECT
        finca,
        flor,
        aass,
        problema,
        tallos_problema,
        SUM(tallos_problema) OVER (
            PARTITION BY finca, flor, aass
        ) AS total_tallos_fuente
    FROM (
        SELECT
            LPAD(TRIM(CAST(n.finca AS CHAR)),3,'0') AS finca,
            TRIM(COALESCE(n.flor,'')) AS flor,
            d.aass,
            TRIM(COALESCE(n.problema,'SIN_PROBLEMA')) AS problema,
            SUM(COALESCE(n.tallos,0)) AS tallos_problema
        FROM ld_nacional n
        LEFT JOIN dates d
            ON d.fecha=DATE(n.fecha)
        WHERE DATE(n.fecha) BETWEEN %s AND %s
          AND UPPER(TRIM(COALESCE(n.fuente,'')))='CULTIVO'
          AND UPPER(TRIM(COALESCE(n.grado,'')))='NAL'
          AND LPAD(TRIM(CAST(n.finca AS CHAR)),3,'0') IN ('001','002')
        GROUP BY 1,2,3,4

        UNION ALL

        SELECT
            '000' AS finca,
            TRIM(COALESCE(n.flor,'')) AS flor,
            d.aass,
            TRIM(COALESCE(n.problema,'SIN_PROBLEMA')) AS problema,
            SUM(COALESCE(n.tallos,0)) AS tallos_problema
        FROM ld_nacional n
        LEFT JOIN dates d
            ON d.fecha=DATE(n.fecha)
        WHERE DATE(n.fecha) BETWEEN %s AND %s
          AND UPPER(TRIM(COALESCE(n.fuente,'')))='CULTIVO'
          AND UPPER(TRIM(COALESCE(n.grado,'')))='NAL'
          AND TRIM(COALESCE(n.flor,'')) IN ('CLA','CM0')
        GROUP BY 2,3,4
    ) sub
),

-- =====================================
-- PROBLEMAS DIRIGIDA
-- =====================================
dirigida_problema AS (
    SELECT
        finca,
        flor,
        aass,
        problema,
        tallos_problema,
        SUM(tallos_problema) OVER (
            PARTITION BY finca, flor, aass
        ) AS total_tallos_fuente
    FROM (
        SELECT
            LPAD(TRIM(CAST(n.finca AS CHAR)),3,'0') AS finca,
            TRIM(COALESCE(n.flor,'')) AS flor,
            d.aass,
            TRIM(COALESCE(n.problema,'SIN_PROBLEMA')) AS problema,
            SUM(COALESCE(n.tallos,0)) AS tallos_problema
        FROM ld_nacional n
        LEFT JOIN dates d
            ON d.fecha = DATE(n.fecha)
        WHERE DATE(n.fecha) BETWEEN %s AND %s
          AND UPPER(TRIM(COALESCE(n.fuente,'')))='DIRIGIDA'
          AND UPPER(TRIM(COALESCE(n.grado,'')))='NAL'
          AND LPAD(TRIM(CAST(n.finca AS CHAR)),3,'0') IN ('001','002')
        GROUP BY 1,2,3,4

        UNION ALL

        SELECT
            '000' AS finca,
            TRIM(COALESCE(n.flor,'')) AS flor,
            d.aass,
            TRIM(COALESCE(n.problema,'SIN_PROBLEMA')) AS problema,
            SUM(COALESCE(n.tallos,0)) AS tallos_problema
        FROM ld_nacional n
        LEFT JOIN dates d
            ON d.fecha = DATE(n.fecha)
        WHERE DATE(n.fecha) BETWEEN %s AND %s
          AND UPPER(TRIM(COALESCE(n.fuente,'')))='DIRIGIDA'
          AND UPPER(TRIM(COALESCE(n.grado,'')))='NAL'
          AND TRIM(COALESCE(n.flor,'')) IN ('CLA','CM0')
        GROUP BY 2,3,4
    ) sub
),

-- =====================================
-- PONDERADOS
-- =====================================
ponderados AS (

    SELECT
        cp.finca,
        cp.flor,
        cp.aass,
        cp.problema,
        (
            cp.tallos_problema / cp.total_tallos_fuente
        ) * bp.porcentaje_fito AS aporte_ponderado
    FROM cultivo_problema cp
    INNER JOIN base_porcentajes bp
        ON bp.finca=cp.finca
       AND bp.flor=cp.flor
       AND bp.aass=cp.aass

    UNION ALL

    SELECT
        dp.finca,
        dp.flor,
        dp.aass,
        dp.problema,
        (
            dp.tallos_problema / dp.total_tallos_fuente
        ) * bp.porcentaje_nacional_dirigida
    FROM dirigida_problema dp
    INNER JOIN base_porcentajes bp
        ON bp.finca=dp.finca
       AND bp.flor=dp.flor
       AND bp.aass=dp.aass
),

aportes_agrupados AS (
    SELECT
        finca,
        flor,
        aass,
        problema,
        SUM(aporte_ponderado) AS aporte_ponderado_sum
    FROM ponderados
    GROUP BY 1,2,3,4
),

aporte_total_grupo AS (
    SELECT
        finca,
        flor,
        aass,
        SUM(aporte_ponderado_sum) AS aporte_total
    FROM aportes_agrupados
    GROUP BY 1,2,3
)

SELECT
    a.finca,
    a.flor,
    a.aass,
    a.problema,
    ROUND(
        a.aporte_ponderado_sum / g.aporte_total,
        6
    ) AS aporte_final
FROM aportes_agrupados a
INNER JOIN aporte_total_grupo g
    ON g.finca=a.finca
   AND g.flor=a.flor
   AND g.aass=a.aass
ORDER BY 1,2,3,4;
"""


def exporta_aportes_ponderados_problemas_excel(
    fecha_inicio: str | None = None,
    fecha_fin: str | None = None,
) -> str:
    params_input: dict[str, str] = {}
    if fecha_inicio:
        params_input["fecha_inicio"] = fecha_inicio
    if fecha_fin:
        params_input["fecha_fin"] = fecha_fin

    ini, fin = resolve_date_range_params(params_input or None)

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

    filename = "aportes_ponderados_problemas.csv"
    output_path = output_dir / filename

    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return str(output_path)


def generate_aportes_ponderados_problemas(params: dict | None = None) -> str:
    params = params or {}
    output_path = exporta_aportes_ponderados_problemas_excel(
        fecha_inicio=params.get("fecha_inicio"),
        fecha_fin=params.get("fecha_fin"),
    )
    return f"csv:{output_path}"
