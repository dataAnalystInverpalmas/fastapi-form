import unittest

import pandas as pd

from app.services.etl_jobs.productivity_varieties_report_generator import (
    _append_all_farms_base_rows,
    _build_cycle_rows,
    _build_total_rows,
)


class ProductivityVarietiesReportTests(unittest.TestCase):
    def test_append_all_farms_base_rows_adds_finca_000_template_rows(self) -> None:
        df_base = pd.DataFrame(
            {
                "flor": ["CLA", "CLA"],
                "orden_color": [1, 1],
                "color": ["BLANCO", "BLANCO"],
                "variedad": ["MOON", "MOON"],
                "finca": ["001", "002"],
                "merge_variedad": ["MOON", "MOON"],
                "_orden_fila": [0, 1],
            }
        )

        result = _append_all_farms_base_rows(df_base)
        finca_000 = result[result["finca"] == "000"].reset_index(drop=True)

        self.assertEqual(len(finca_000), 1)
        self.assertEqual(finca_000.loc[0, "variedad"], "MOON")
        self.assertEqual(finca_000.loc[0, "_orden_fila"], 0)

    def test_build_cycle_rows_keeps_peak_for_each_cycle_by_finca_and_variety(self) -> None:
        df_base = pd.DataFrame(
            {
                "flor": ["CLA", "CLA"],
                "orden_color": [1, 1],
                "color": ["BLANCO", "BLANCO"],
                "variedad": ["MOON", "MOON"],
                "finca": ["001", "000"],
                "merge_variedad": ["MOON", "MOON"],
                "_orden_fila": [0, 0],
            }
        )
        df_prod = pd.DataFrame(
            {
                "finca": ["001", "001", "000", "000"],
                "merge_variedad": ["MOON", "MOON", "MOON", "MOON"],
                "ciclo": [1, 2, 1, 2],
                "f_m": [3.25, 4.5, 7.5, 9.0],
                "pico": [25, 45, 24, 44],
            }
        )
        df_fusarium = pd.DataFrame(
            {
                "finca": ["001", "001", "000", "000"],
                "merge_variedad": ["MOON", "MOON", "MOON", "MOON"],
                "ciclo": [1, 2, 1, 2],
                "fusarium": [0.1234, 0.2345, 0.3, 0.4],
            }
        )

        result = _build_cycle_rows(df_base=df_base, df_prod=df_prod, df_fusarium=df_fusarium)

        self.assertEqual(result["finca"].tolist(), ["001", "001", "000", "000"])
        self.assertEqual(result["ciclo"].tolist(), ["1", "2", "1", "2"])
        self.assertEqual(result["Pico"].tolist(), [25, 45, 24, 44])

    def test_build_total_rows_consumes_finca_000_from_upstream_summaries(self) -> None:
        df_base = pd.DataFrame(
            {
                "flor": ["CLA", "CLA"],
                "orden_color": [1, 1],
                "color": ["BLANCO", "BLANCO"],
                "variedad": ["MOON", "MOON"],
                "finca": ["001", "000"],
                "merge_variedad": ["MOON", "MOON"],
                "_orden_fila": [0, 0],
            }
        )
        df_prod = pd.DataFrame(
            {
                "finca": ["001", "001", "000", "000"],
                "merge_variedad": ["MOON", "MOON", "MOON", "MOON"],
                "ciclo": [1, 2, 1, 2],
                "f_m": [3.25, 4.5, 7.5, 9.0],
                "pico": [25, 45, 24, 44],
            }
        )
        df_qualities = pd.DataFrame(
            {
                "finca": ["001", "000"],
                "merge_variedad": ["MOON", "MOON"],
                "SEL": [40, 70],
                "FAN": [20, 30],
                "STD": [30, 70],
                "SHR": [5, 15],
                "NAL": [5, 15],
            }
        )

        result = _build_total_rows(df_base=df_base, df_prod=df_prod, df_qualities=df_qualities)
        finca_000 = result[result["finca"] == "000"].reset_index(drop=True)

        self.assertEqual(len(finca_000), 1)
        self.assertEqual(finca_000.loc[0, "Flor Mata"], 16.5)
        self.assertEqual(finca_000.loc[0, "SEL"], 70)
        self.assertEqual(finca_000.loc[0, "STD"], 70)


if __name__ == "__main__":
    unittest.main()