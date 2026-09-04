import unittest

import pandas as pd

from app.services.etl_jobs.anomalias_lonas_generator import _analyze_group


class AnomaliasLonasTests(unittest.TestCase):
    def test_zero_tallos_is_not_flagged_as_missing_data(self) -> None:
        fechas = pd.date_range("2026-01-05", periods=8, freq="D")
        group_df = pd.DataFrame(
            {
                "fecha_registro": fechas,
                "tallos": [20, 20, 20, 20, 20, 20, 20, 0],
                "plantas": [100] * 8,
                "flor": [0] * 8,
                "finca": ["001"] * 8,
                "bloque": [1] * 8,
                "variedad": ["MOON"] * 8,
                "cosecha": [2026] * 8,
            }
        )

        result = _analyze_group(
            group_df=group_df,
            siembra_yyww=2601,
            plantas_ref=100,
            festivos=set(),
        )

        row = result.loc[result["fecha_registro"] == pd.Timestamp("2026-01-12")].iloc[0]
        self.assertFalse(row["es_anomalo"])
        self.assertEqual(row["motivo"], "normal")


if __name__ == "__main__":
    unittest.main()