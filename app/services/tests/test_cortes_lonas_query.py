import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app.services.queries.cortes_lonas_query import _agrupar_sin_bloque, _escribir_en_partes


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


class AgruparSinBloqueTests(unittest.TestCase):
    def test_suma_bloques_y_siembras_en_una_fila_con_2401(self):
        df = pd.DataFrame(
            {
                "variedad": ["A", "A", "A", "A", "B"],
                "finca": ["F1", "F1", "F1", "F1", "F2"],
                "bloque": ["12", "18", "12", "12", "2"],
                "semana": [2640, 2640, 2640, 2641, 2640],
                "semana_siembra": [None, 2310, 2401, None, 2320],
                "cantidad": [10, 5, 7, 4, 3],
            }
        )
        out = _agrupar_sin_bloque(df, 2401)
        self.assertEqual(
            out.columns.tolist(), ["variedad", "finca", "bloque", "semana", "semana_siembra", "cantidad"]
        )
        self.assertEqual(
            out.values.tolist(),
            [
                ["A", "F1", "", 2640, 2401, 22],
                ["A", "F1", "", 2641, 2401, 4],
                ["B", "F2", "", 2640, 2401, 3],
            ],
        )


if __name__ == "__main__":
    unittest.main()
