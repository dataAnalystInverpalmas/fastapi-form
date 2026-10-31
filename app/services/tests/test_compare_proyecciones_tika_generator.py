import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app.services.etl_jobs import compare_proyecciones_tika_generator as gen


def _frame(tipo: str, tallos) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fecha": [pd.Timestamp("2026-01-05")],
            "flor": ["CLA"],
            "variedad": ["VAR_A"],
            "color": ["ROJO"],
            "tallos": [tallos],
            "tipo": [tipo],
        }
    )


class CompareProyeccionesTikaDemandaTest(unittest.TestCase):
    def test_agrega_demanda_una_sola_vez(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "escenarios.csv"
            fuentes = {"proyecciones": lambda modelo, tipo, d, v: _frame(tipo, 10)}
            # _load_demanda devuelve tallos como Int64 (nullable)
            demanda = _frame("demanda", 25).astype({"tallos": "Int64"})
            with (
                patch.object(gen, "FUENTES", fuentes),
                patch.object(gen, "_load_dates_and_variedades", return_value=(None, None)),
                patch.object(gen, "_load_demanda", return_value=demanda) as load_demanda,
                patch.object(gen.settings, "COMPARE_PROYECCIONES_TIKA_OUTPUT_PATH", str(output)),
                patch.object(gen, "dataframe_to_sql") as to_sql,
            ):
                gen.generate_compare_proyecciones_tika_report({"modelos_tika": [1, 2]})

            load_demanda.assert_called_once()
            df = to_sql.call_args.args[0]
            self.assertEqual(sorted(df["tipo"].unique()), ["Tika_1", "Tika_2", "demanda"])
            dem = df[df["fuente"] == "demanda"]
            self.assertEqual(len(dem), 1)
            self.assertEqual(dem["tipo"].iloc[0], "demanda")
            self.assertEqual(dem["tallos"].iloc[0], 25)
            self.assertIn("demanda", pd.read_csv(output)["fuente"].tolist())


if __name__ == "__main__":
    unittest.main()
