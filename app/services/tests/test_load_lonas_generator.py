import unittest

import pandas as pd

from app.services.dbf_loaders.load_lonas_generator import prepare_lonas_dataframe, select_recent_files


class LoadLonasGeneratorTests(unittest.TestCase):
    def test_select_recent_files_keeps_cutoff_year_and_newer(self) -> None:
        files = ["lonas2026.dbf", "LONAS2025.DBF", "lonas2024.dbf", "lonas2016.dbf"]
        self.assertEqual(select_recent_files(files, 2025), ["lonas2026.dbf", "LONAS2025.DBF"])

    def test_prepare_renames_and_fills_flor_from_catalog(self) -> None:
        df_lonas = pd.DataFrame(
            {
                "fecha": ["2026-01-05", None],
                "fsiemb": ["2025-06-01", "2025-06-01"],
                "finca": ["001", "002"],
                "bloque": [1, 2],
                "cosecha": ["1", "1"],
                "flor": [None, "CLA"],
                "variedad": ["V1", "V1"],
                "lonas": [10, 20],
                "tmatab": [30, 40],
            }
        )
        df_vari = pd.DataFrame({"codigo": ["V1"], "nombre": ["Variedad Uno"], "codflor": ["CM0"]})

        result = prepare_lonas_dataframe(df_lonas, df_vari)

        self.assertEqual(
            list(result.columns),
            ["fecha", "fecha_siembra", "finca", "bloque", "cosecha", "flor", "variedad", "tallos", "plantas"],
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result["flor"].tolist(), ["CM0"])
        self.assertEqual(result["variedad"].tolist(), ["Variedad Uno"])


if __name__ == "__main__":
    unittest.main()
