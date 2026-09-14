import unittest

import pandas as pd

from app.services.tika_loaders.load_tika_demanda_generator import prepare_tika_demanda_dataframe


class LoadTikaDemandaGeneratorTests(unittest.TestCase):
    def test_renames_and_coerces_types(self) -> None:
        df = pd.DataFrame(
            {
                "Flor": ["CLAVEL"],
                "Color": ["LILA"],
                "Item Demanda": ["FARIDA"],
                "Tipo": ["TALLOS"],
                "Mercado": ["ORDEN_FIJA"],
                "Submercado": ["ORDEN_FIJA"],
                "Semana": ["2601"],
                "Semana enraizamiento": ["2601"],
                "Fecha": ["2025-12-29"],
                "Cantidad": ["11.000"],
                "Cantidad para enraizar": ["6.500"],
                "Precio": ["0.17"],
                "Grupo de demanda": ["demanda_27-28v4"],
                "Editar": [""],
                "Eliminar": [""],
            }
        )

        result = prepare_tika_demanda_dataframe(df)

        self.assertEqual(
            list(result.columns),
            [
                "flor",
                "color",
                "item_demanda",
                "tipo",
                "mercado",
                "submercado",
                "semana",
                "semana_enraizamiento",
                "fecha",
                "cantidad",
                "cantidad_enraizar",
                "precio",
                "grupo_demanda",
            ],
        )
        self.assertEqual(result["flor"].tolist(), ["CLAVEL"])
        self.assertEqual(result["semana"].tolist(), ["2601"])
        self.assertEqual(result["fecha"].dt.strftime("%Y-%m-%d").tolist(), ["2025-12-29"])
        self.assertEqual(result["cantidad"].tolist(), [11000.0])
        self.assertEqual(result["cantidad_enraizar"].tolist(), [6500.0])
        self.assertEqual(result["precio"].tolist(), [0.17])

    def test_missing_columns_raise(self) -> None:
        df = pd.DataFrame({"Flor": ["CLAVEL"]})
        with self.assertRaises(ValueError):
            prepare_tika_demanda_dataframe(df)


if __name__ == "__main__":
    unittest.main()
