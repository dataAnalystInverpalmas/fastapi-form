import os
import tempfile
import unittest

import pandas as pd

from app.core.settings import settings
from app.services.etl_jobs.quipus_vs_proy_generator import _load_plano_data


class QuipusVsProySchemaTests(unittest.TestCase):
    def test_load_plano_data_accepts_programada_arranque_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "tika-plano-siembra-prueba.csv")
            pd.DataFrame(
                [{
                    "Finca": "001",
                    "Bloque": "10",
                    "Variedad": "Rosa",
                    "Flor": "CLA",
                    "Estado": "Sembrada",
                    "Semana": 2501,
                    "S. arranque programada": 2515,
                    "S. arranque real": 2516,
                    "Fiesta (pico)": "2025",
                    "Esquejes sembrados": 120,
                }]
            ).to_csv(csv_path, index=False)

            original_path = settings.QUIPUS_PLANO_PATH
            settings.QUIPUS_PLANO_PATH = csv_path
            try:
                df_plano_group_s, df_plano_group_a, df_plano_final, df_nplantas = _load_plano_data(2500)
            finally:
                settings.QUIPUS_PLANO_PATH = original_path

        self.assertFalse(df_plano_group_s.empty)
        self.assertIn("farranque", df_plano_group_s.columns)
        self.assertFalse(df_nplantas.empty)
        self.assertEqual(df_nplantas.iloc[0]["cosecha"], "2025")


if __name__ == "__main__":
    unittest.main()
