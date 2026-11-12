import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app.services.queries.cortes_lonas_query import _escribir_en_partes


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


if __name__ == "__main__":
    unittest.main()
