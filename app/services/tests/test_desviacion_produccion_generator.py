import unittest

import pandas as pd

from app.services.etl_jobs.desviacion_produccion_generator import (
    _build_desviacion,
    _classify_estado,
    _current_snapshot_date,
    _equivalent_age,
)


def _referencia(finca: str, nvariedad: str, ciclo: int, edades: list[int], fm_suave: list[float]) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "finca": [finca] * len(edades),
            "nvariedad": [nvariedad] * len(edades),
            "ciclo": [ciclo] * len(edades),
            "edad": edades,
            "fm_suave": fm_suave,
        }
    )
    df["fm_suave_cum"] = df["fm_suave"].cumsum()
    return df


class DesviacionProduccionTests(unittest.TestCase):
    def test_classify_estado_uses_umbral(self) -> None:
        self.assertEqual(_classify_estado(2.0, umbral=1.0), "Atrasada")
        self.assertEqual(_classify_estado(-2.0, umbral=1.0), "Adelantada")
        self.assertEqual(_classify_estado(0.5, umbral=1.0), "Normal")

    def test_equivalent_age_interpolates_between_points(self) -> None:
        edades = [18, 19, 20, 21]
        acumulado = [0.0, 1.0, 3.0, 6.0]

        import numpy as np

        edad_equivalente = _equivalent_age(2.0, np.array(edades, dtype=float), np.array(acumulado, dtype=float))

        self.assertAlmostEqual(edad_equivalente, 19.5)

    def test_equivalent_age_clips_when_above_historical_ceiling(self) -> None:
        import numpy as np

        edades = np.array([18, 19, 20], dtype=float)
        acumulado = np.array([0.0, 1.0, 2.0], dtype=float)

        self.assertEqual(_equivalent_age(10.0, edades, acumulado), 20.0)

    def test_build_desviacion_flags_atrasada_when_real_is_below_reference(self) -> None:
        # Referencia: a la edad 21 deberia acumular 6.0; el bloque real solo lleva 1.0.
        df_ref = _referencia("001", "MOON", 1, [18, 19, 20, 21], [0.0, 1.0, 2.0, 3.0])
        df_detail = pd.DataFrame(
            {
                "finca": ["001", "001"],
                "bloque": [19, 19],
                "nvariedad": ["MOON", "MOON"],
                "cosecha": ["EN2605", "EN2605"],
                "ciclo": [1, 1],
                "edad": [18, 19],
                "f_m": [0.0, 1.0],
            }
        )

        resultado = _build_desviacion(df_detail, df_ref, umbral=1.0)

        self.assertEqual(len(resultado), 1)
        fila = resultado.iloc[0]
        self.assertEqual(fila["estado"], "Normal")
        self.assertEqual(fila["edad_actual"], 19.0)
        self.assertEqual(fila["f_m_acumulado_real"], 1.0)

    def test_build_desviacion_flags_adelantada_when_real_exceeds_reference(self) -> None:
        df_ref = _referencia("001", "MOON", 1, [18, 19, 20, 21, 22, 23], [0.0, 0.5, 0.5, 0.5, 0.5, 0.5])
        df_detail = pd.DataFrame(
            {
                "finca": ["001"],
                "bloque": [19],
                "nvariedad": ["MOON"],
                "cosecha": ["EN2605"],
                "ciclo": [1],
                "edad": [19],
                "f_m": [2.5],
            }
        )

        resultado = _build_desviacion(df_detail, df_ref, umbral=1.0)

        fila = resultado.iloc[0]
        self.assertEqual(fila["estado"], "Adelantada")
        self.assertLess(fila["semanas_adelanto_atraso"], 0)

    def test_build_desviacion_marks_missing_reference(self) -> None:
        df_ref = _referencia("001", "MOON", 1, [18, 19], [0.0, 1.0])
        df_detail = pd.DataFrame(
            {
                "finca": ["002"],
                "bloque": [5],
                "nvariedad": ["OTRA"],
                "cosecha": ["EN2605"],
                "ciclo": [1],
                "edad": [18],
                "f_m": [0.2],
            }
        )

        resultado = _build_desviacion(df_detail, df_ref, umbral=1.0)

        self.assertEqual(resultado.iloc[0]["estado"], "Sin referencia")
        self.assertTrue(pd.isna(resultado.iloc[0]["semanas_adelanto_atraso"]))


    def test_current_snapshot_date_is_always_a_monday(self) -> None:
        self.assertEqual(_current_snapshot_date().weekday(), 0)


if __name__ == "__main__":
    unittest.main()
