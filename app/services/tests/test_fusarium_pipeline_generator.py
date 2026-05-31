import unittest

import pandas as pd

from app.services.etl_jobs.fusarium_pipeline_generator import _build_fusarium_export


class FusariumPipelineTests(unittest.TestCase):
    def test_build_fusarium_export_appends_finca_000_grouped_without_finca(self) -> None:
        df_fusarium = pd.DataFrame(
            {
                "fecha": pd.to_datetime(["2026-01-01", "2026-01-01"]),
                "finca": ["001", "002"],
                "variedad": ["MOON", "MOON"],
                "ciclo": [1, 1],
                "fusarium": [0.2, 0.4],
            }
        )

        result = _build_fusarium_export(df_fusarium)
        finca_000 = result[result["finca"] == "000"].reset_index(drop=True)

        self.assertEqual(len(finca_000), 1)
        self.assertEqual(finca_000.loc[0, "variedad"], "MOON")
        self.assertEqual(finca_000.loc[0, "ciclo"], 1)
        self.assertAlmostEqual(finca_000.loc[0, "fusarium"], 0.3)


if __name__ == "__main__":
    unittest.main()