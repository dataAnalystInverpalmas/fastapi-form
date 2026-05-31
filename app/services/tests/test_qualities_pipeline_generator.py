import unittest

import pandas as pd

from app.services.etl_jobs.qualities_pipeline_generator import _build_qualities_export_rows


class QualitiesPipelineTests(unittest.TestCase):
    def test_build_qualities_export_rows_appends_finca_000_grouped_without_finca(self) -> None:
        df_cal = pd.DataFrame(
            {
                "finca": ["001", "001", "002", "002"],
                "nvari": ["MOON", "MOON", "MOON", "MOON"],
                "grado": ["SEL", "STD", "SEL", "STD"],
                "tallos": [40, 60, 30, 70],
            }
        )

        result = _build_qualities_export_rows(df_cal)
        finca_000 = result[result["finca"] == "000"].sort_values("grado").reset_index(drop=True)

        self.assertEqual(len(finca_000), 2)
        self.assertEqual(finca_000["grado"].tolist(), ["SEL", "STD"])
        self.assertAlmostEqual(finca_000.loc[0, "aporte"], 0.35)
        self.assertAlmostEqual(finca_000.loc[1, "aporte"], 0.65)


if __name__ == "__main__":
    unittest.main()