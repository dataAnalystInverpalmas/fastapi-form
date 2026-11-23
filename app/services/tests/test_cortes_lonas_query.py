import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app.services.queries.arreglos_tika_query import preparar_arreglos_tika
from app.services.queries.cortes_lonas_query import _escribir_en_partes, formato_tika


class EscribirEnPartesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _df(self, n):
        return pd.DataFrame({"variedad": ["A"] * n, "cantidad": range(1, n + 1)})

    def test_hasta_el_maximo_un_solo_archivo(self):
        paths = _escribir_en_partes(self._df(1000), self.dir, "base", 1000)
        self.assertEqual([p.name for p in paths], ["base.xlsx"])
        self.assertEqual(len(pd.read_excel(paths[0])), 1000)

    def test_mas_del_maximo_se_parte(self):
        paths = _escribir_en_partes(self._df(2501), self.dir, "base", 1000)
        self.assertEqual(
            [p.name for p in paths],
            ["base_parte01.xlsx", "base_parte02.xlsx", "base_parte03.xlsx"],
        )
        partes = [pd.read_excel(p) for p in paths]
        self.assertEqual([len(p) for p in partes], [1000, 1000, 501])
        self.assertEqual(pd.concat(partes)["cantidad"].tolist(), list(range(1, 2502)))
        self.assertFalse((self.dir / "base.xlsx").exists())

    def test_borra_partes_viejas_del_mismo_rango(self):
        _escribir_en_partes(self._df(3000), self.dir, "base", 1000)
        (self.dir / "otro_parte01.xlsx").touch()
        _escribir_en_partes(self._df(10), self.dir, "base", 1000)
        self.assertEqual(
            sorted(p.name for p in self.dir.iterdir()), ["base.xlsx", "otro_parte01.xlsx"]
        )


class FormatoTikaTests(unittest.TestCase):
    def test_cortes_rosas_suma_semanas_y_usa_guion_bajo(self):
        df = pd.DataFrame(
            {
                "finca": ["INVERPALMAS", "INVERPALMAS", "INVERPALMAS", "PALERMO", "INVERPALMAS"],
                "bloque": ["9", "9", "10", "2", "9"],
                "variedad": ["CARMESI", "CARMESI", "PINK FLOYD", "CARMESI", "SIN CORTE"],
                "tipo": "CORTE_REAL",
                "cantidad": [60, 40, 5, 3, 0],
            }
        )
        out = formato_tika(df)
        self.assertEqual(out.columns.tolist(), ["Finca", "Bloque", "Variedad", "Tipo", "Cantidad"])
        self.assertEqual(
            out.values.tolist(),
            [
                ["INVERPALMAS", "9", "CARMESI", "CORTE_REAL", 100],
                ["INVERPALMAS", "10", "PINK_FLOYD", "CORTE_REAL", 5],
                ["PALERMO", "2", "CARMESI", "CORTE_REAL", 3],
            ],
        )

    def test_arreglos_conserva_tipo_y_mapea_finca(self):
        df = pd.DataFrame(
            {
                "finca": ["001", "1", "002"],
                "bloque": [9.0, 9.0, 3.0],
                "variedad": ["FREE SPIRIT", "FREE SPIRIT", "CARMESI"],
                "tipo": ["AR", "AR", "PODA SANITARIA"],
                "cantidad": [10, 15, 7],
            }
        )
        out = preparar_arreglos_tika(df)
        self.assertEqual(
            out.values.tolist(),
            [
                ["INVERPALMAS", "9", "FREE_SPIRIT", "AR", 25],
                ["PALERMO", "3", "CARMESI", "PODA_SANITARIA", 7],
            ],
        )


if __name__ == "__main__":
    unittest.main()
