import unittest

import pandas as pd

from app.services.etl_jobs.resumir_curvas_usadas_generator import _apply_curve_filter


class ResumirCurvasUsadasFilterTests(unittest.TestCase):
    def test_apply_curve_filter_marks_groups_by_cycle_and_percentiles(self) -> None:
        rows = []

        cycle_1_sums = [10, 20, 30, 40, 50]
        for index, suma_fm in enumerate(cycle_1_sums, start=1):
            rows.extend(
                {
                    "prg": 2020 + index,
                    "variedad": "MOON",
                    "ciclo": 1,
                    "edad": edad,
                    "fm": suma_fm / 9,
                }
                for edad in range(1, 10)
            )

        cycle_2_sums = [100, 200, 300, 400, 500]
        for index, suma_fm in enumerate(cycle_2_sums, start=1):
            rows.extend(
                {
                    "prg": 2030 + index,
                    "variedad": "MOON",
                    "ciclo": 2,
                    "edad": edad,
                    "fm": suma_fm / 15,
                }
                for edad in range(36, 51)
            )

        df = pd.DataFrame(rows)
        resultado = _apply_curve_filter(df, ["prg", "variedad", "ciclo"], "variedad")

        filtros_ciclo_1 = (
            resultado[resultado["ciclo"] == 1]
            .groupby("prg", as_index=False)["filtro"]
            .first()
            .sort_values("prg")
            ["filtro"]
            .tolist()
        )
        filtros_ciclo_2 = (
            resultado[resultado["ciclo"] == 2]
            .groupby("prg", as_index=False)["filtro"]
            .first()
            .sort_values("prg")
            ["filtro"]
            .tolist()
        )

        self.assertEqual(filtros_ciclo_1, [0, 1, 1, 1, 0])
        self.assertEqual(filtros_ciclo_2, [0, 1, 1, 1, 0])


if __name__ == "__main__":
    unittest.main()