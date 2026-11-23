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
    def test_cortes_rosas_por_semana_y_con_guion_bajo(self):
        df = pd.DataFrame(
            {
                "finca": ["INVERPALMAS", "INVERPALMAS", "INVERPALMAS", "INVERPALMAS", "PALERMO", "INVERPALMAS"],
                "bloque": ["9", "9", "9", "10", "2", "9"],
                "variedad": ["CARMESI", "CARMESI", "CARMESI", "PINK FLOYD", "CARMESI", "SIN CORTE"],
                "semana": [2646, 2646, 2645, 2645, 2645, 2645],
                "semana_siembra": [None, 2310, 2310, None, None, None],
                "tipo": "CORTE_REAL",
                "cantidad": [60, 40, 8, 5, 3, 0],
            }
        )
        out = formato_tika(df)
        self.assertEqual(
            out.columns.tolist(), ["Finca", "Bloque", "Variedad", "Semana", "Tipo", "Cantidad"]
        )
        self.assertEqual(
            out.values.tolist(),
            [
                ["INVERPALMAS", "9", "CARMESI", 2645, "CORTE_REAL", 8],
                ["INVERPALMAS", "9", "CARMESI", 2646, "CORTE_REAL", 100],
                ["INVERPALMAS", "10", "PINK_FLOYD", 2645, "CORTE_REAL", 5],
                ["PALERMO", "2", "CARMESI", 2645, "CORTE_REAL", 3],
            ],
        )

    def test_arreglos_renombra_tipos_y_mapea_finca(self):
        df = pd.DataFrame(
            {
                "finca": ["001", "1", "002", "002", "001", "001", "002"],
                "bloque": [9.0, 9.0, 3.0, 3.0, 4.0, 4.0, 5.0],
                "variedad": ["FREE SPIRIT", "FREE SPIRIT", "CARMESI", "CARMESI", "CARMESI", "CARMESI", "CARMESI"],
                "tipo": ["AR", "AR", "BA", "S1", "S2", "S3", "DC"],
                "cantidad": [10, 15, 7, 1, 2, 3, 4],
            }
        )
        out = preparar_arreglos_tika(df)
        self.assertEqual(out.columns.tolist(), ["Finca", "Bloque", "Variedad", "Tipo", "Cantidad"])
        self.assertEqual(
            out.values.tolist(),
            [
                ["INVERPALMAS", "4", "CARMESI", "Selectiva_2", 2],
                ["INVERPALMAS", "4", "CARMESI", "Selectiva_3", 3],
                ["INVERPALMAS", "9", "FREE_SPIRIT", "Poda_AR", 25],
                ["PALERMO", "3", "CARMESI", "Poda_BA", 7],
                ["PALERMO", "3", "CARMESI", "Selectiva_1", 1],
                ["PALERMO", "5", "CARMESI", "DC", 4],
            ],
        )


if __name__ == "__main__":
    unittest.main()
