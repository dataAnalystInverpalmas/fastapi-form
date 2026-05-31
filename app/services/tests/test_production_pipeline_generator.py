import unittest

import pandas as pd

from app.services.etl_jobs.production_pipeline_generator import (
    _annotate_cycle_peaks,
    _build_summary,
    _calculate_peak_age,
    _smooth_curves,
)


class ProductionPipelinePeakTests(unittest.TestCase):
    def test_calculate_peak_age_cycle_1_uses_last_age_of_best_consecutive_4_points(self) -> None:
        grupo = pd.DataFrame(
            {
                "edad": [18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33],
                "ciclo": [1] * 16,
                "f_m": [
                    0.000689686,
                    0.002313785,
                    0.040891697,
                    0.209508766,
                    0.693801726,
                    0.811493281,
                    1.060625612,
                    0.646969832,
                    0.504805553,
                    0.43806176,
                    0.32215004,
                    0.174134555,
                    0.185102785,
                    0.084853609,
                    0.008543205,
                    0.003047967,
                ],
            }
        )

        self.assertEqual(_calculate_peak_age(grupo), 25.0)

    def test_calculate_peak_age_cycle_2_uses_last_age_of_best_consecutive_10_points(self) -> None:
        grupo = pd.DataFrame(
            {
                "edad": list(range(36, 51)),
                "ciclo": [2] * 15,
                "f_m": [1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 0.3, 0.2, 0.1, 0.0, 0.0],
            }
        )

        self.assertEqual(_calculate_peak_age(grupo), 45.0)

    def test_annotate_cycle_peaks_keeps_detail_groups_separate(self) -> None:
        detalle = pd.DataFrame(
            {
                "finca": ["001"] * 10,
                "bloque": [19, 19, 19, 19, 20, 20, 20, 20, 20, 20],
                "nvariedad": ["MOON"] * 10,
                "cosecha": ["EN2605"] * 10,
                "ciclo": [1] * 10,
                "edad": [22, 23, 24, 25, 18, 19, 20, 21, 22, 23],
                "f_m": [0.69, 0.81, 1.06, 0.64, 0.05, 0.10, 0.15, 0.90, 0.95, 1.00],
            }
        )

        resultado = _annotate_cycle_peaks(
            detalle,
            ["finca", "bloque", "nvariedad", "cosecha", "ciclo"],
        )

        bloque_19 = resultado.loc[resultado["bloque"] == 19, "pico"].dropna().unique().tolist()
        bloque_20 = resultado.loc[resultado["bloque"] == 20, "pico"].dropna().unique().tolist()

        self.assertEqual(bloque_19, [25])
        self.assertEqual(bloque_20, [23])

    def test_smooth_curves_keeps_each_detail_curve_total_separate(self) -> None:
        detalle = pd.DataFrame(
            {
                "finca": ["001"] * 8,
                "bloque": [19, 19, 19, 19, 20, 20, 20, 20],
                "nvariedad": ["MOON"] * 8,
                "cosecha": ["EN2605"] * 4 + ["EN2606"] * 4,
                "edad": [18, 19, 20, 21, 18, 19, 20, 21],
                "ciclo": [1] * 8,
                "f_m": [1.0, 1.0, 1.0, 1.0, 10.0, 10.0, 10.0, 10.0],
            }
        )

        resultado = _smooth_curves(
            detalle,
            {
                "sem_valle": 0,
                "peak_window_weeks": 4,
                "smooth_window_length": 3,
                "smooth_polyorder": 1,
                "force_valley_weeks_after_peak": 0,
            },
        )

        sumas = (
            resultado.groupby(["bloque", "cosecha"], as_index=False)[["f_m", "fm_suave"]]
            .sum()
            .sort_values(["bloque", "cosecha"])
            .reset_index(drop=True)
        )

        esperado = pd.DataFrame(
            {
                "bloque": [19, 20],
                "cosecha": ["EN2605", "EN2606"],
                "f_m": [4.0, 40.0],
                "fm_suave": [4.0, 40.0],
            }
        )

        pd.testing.assert_frame_equal(sumas, esperado, atol=1e-9, rtol=1e-9)

    def test_build_summary_appends_finca_000_grouped_without_finca(self) -> None:
        detalle = pd.DataFrame(
            {
                "finca": ["001", "001", "001", "001", "002", "002", "002", "002"],
                "bloque": [19, 19, 19, 19, 20, 20, 20, 20],
                "nvariedad": ["MOON"] * 8,
                "cosecha": ["EN2605"] * 8,
                "ciclo": [1] * 8,
                "edad": [22, 23, 24, 25, 22, 23, 24, 25],
                "f_m": [0.69, 0.81, 1.06, 0.64, 0.50, 0.55, 0.60, 0.65],
                "fm_suave": [0.69, 0.81, 1.06, 0.64, 0.50, 0.55, 0.60, 0.65],
                "pico": [25] * 8,
            }
        )

        resumen = _build_summary(detalle)

        fincas = resumen["finca"].tolist()
        self.assertEqual(fincas, ["000", "001", "002"])

        finca_000 = resumen[resumen["finca"] == "000"].reset_index(drop=True)
        self.assertEqual(finca_000.loc[0, "nvariedad"], "MOON")
        self.assertEqual(finca_000.loc[0, "ciclo"], 1)
        self.assertEqual(finca_000.loc[0, "pico"], 25)
        self.assertAlmostEqual(finca_000.loc[0, "f_m"], 2.75)


if __name__ == "__main__":
    unittest.main()