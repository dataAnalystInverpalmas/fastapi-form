import unittest

import pandas as pd

from app.services.dbf_loaders.load_arre_generator import prepare_arre_dataframe


class LoadArreGeneratorTests(unittest.TestCase):
    def test_filters_non_ma_and_year_range(self) -> None:
        df = pd.DataFrame(
            {
                "tipo": ["MA", "CL", "CL", "CL"],
                "fecha": ["2020-01-10", "2021-02-11", "2026-03-12", "2019-04-13"],
                "finca": ["001", "002", "003", "004"],
                "flor": ["CLA", "CLA", "CLA", "CLA"],
                "variedad": ["V1", "V2", "V3", "V4"],
                "bloque": [1, 2, 3, 4],
                "tallos": [10, 20, 30, 40],
                "cosecha": ["2020", "2021", "2026", "2019"],
            }
        )

        variedades_catalog = pd.DataFrame(
            {
                "codigo": ["V2", "V3"],
                "nombre": ["Variedad Dos", "Variedad Tres"],
            }
        )

        result = prepare_arre_dataframe(df, variedades_catalog=variedades_catalog)

        self.assertEqual(
            list(result.columns),
            ["tipo", "fecha", "finca", "flor", "variedad", "bloque", "tallos", "cosecha", "nombre_variedad"],
        )
        self.assertEqual(result["tipo"].tolist(), ["CL", "CL"])
        self.assertEqual(result["finca"].tolist(), ["002", "003"])
        self.assertEqual(result["fecha"].dt.year.tolist(), [2021, 2026])
        self.assertEqual(result["nombre_variedad"].tolist(), ["Variedad Dos", "Variedad Tres"])
        self.assertEqual(result["cosecha"].tolist(), ["2021", "2026"])


if __name__ == "__main__":
    unittest.main()
