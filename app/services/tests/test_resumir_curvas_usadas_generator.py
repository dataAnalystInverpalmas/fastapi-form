import unittest
from unittest.mock import patch

import pandas as pd

from app.services.etl_jobs.resumir_curvas_usadas_generator import (
    _apply_curve_filter,
    _build_curvas_resumen_todas,
    _calcular_usemana,
    _resolve_curve_sources,
)


class ResumirCurvasUsadasFilterTests(unittest.TestCase):
    def test_calcular_usemana_cycle_2_uses_10_age_window(self) -> None:
        grupo = pd.DataFrame(
            {
                "edad": list(range(36, 51)),
                "fm": [1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 0.3, 0.2, 0.1, 0.0, 0.0],
                "ciclo": [2] * 15,
            }
        )

        resultado = _calcular_usemana(grupo)

        self.assertEqual(int(resultado["pico"].dropna().iloc[0]), 45)

    def test_resolve_curve_sources_accepts_string_lists(self) -> None:
        resultado = _resolve_curve_sources(
            {
                "curve_paths": "//srv/curvas/2025.csv\n//srv/curvas/2026.csv",
                "curve_years": "2025, 2026",
            }
        )

        self.assertEqual(
            resultado,
            [
                ("//srv/curvas/2025.csv", "2025"),
                ("//srv/curvas/2026.csv", "2026"),
            ],
        )

    def test_resolve_curve_sources_accepts_named_program_and_int_years(self) -> None:
        resultado = _resolve_curve_sources(
            {
                "curve_paths": ["//srv/a.csv", "//srv/b.csv"],
                "curve_years": [2027, "sugerencia_khipus"],
            }
        )

        self.assertEqual(resultado, [("//srv/a.csv", "2027"), ("//srv/b.csv", "sugerencia_khipus")])

    def test_resolve_curve_sources_rejects_duplicated_labels(self) -> None:
        with self.assertRaises(ValueError):
            _resolve_curve_sources(
                {"curve_paths": ["//srv/a.csv", "//srv/b.csv"], "curve_years": ["2026", 2026]}
            )

    def test_build_curvas_resumen_todas_returns_empty_frame_when_source_table_has_no_rows(self) -> None:
        with patch("app.services.etl_jobs.resumir_curvas_usadas_generator.execute_query", return_value=[]):
            resultado = _build_curvas_resumen_todas(export_filter_min=2)

        self.assertIsInstance(resultado, pd.DataFrame)
        self.assertTrue(resultado.empty)

    def test_apply_curve_filter_marks_groups_by_cycle_percentiles_and_peak_mode(self) -> None:
        rows = []

        cycle_1_sums = [10, 20, 30, 40, 100]
        cycle_1_peaks = [20, 21, 22, 27, 28]
        for index, (suma_fm, pico) in enumerate(zip(cycle_1_sums, cycle_1_peaks, strict=True), start=1):
            rows.extend(
                {
                    "prg": 2020 + index,
                    "variedad": "MOON",
                    "ciclo": 1,
                    "edad": edad,
                    "fm": suma_fm / 9,
                    "pico": pico,
                }
                for edad in range(1, 10)
            )

        cycle_2_sums = [100, 200, 300, 400, 1000]
        cycle_2_peaks = [45, 46, 47, 52, 60]
        for index, (suma_fm, pico) in enumerate(zip(cycle_2_sums, cycle_2_peaks, strict=True), start=1):
            rows.extend(
                {
                    "prg": 2030 + index,
                    "variedad": "MOON",
                    "ciclo": 2,
                    "edad": edad,
                    "fm": suma_fm / 15,
                    "pico": pico,
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

        self.assertEqual(filtros_ciclo_1, [2, 2, 2, 1, 0])
        self.assertEqual(filtros_ciclo_2, [2, 2, 2, 1, 0])


if __name__ == "__main__":
    unittest.main()