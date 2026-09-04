import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.utils.dbf_reader import export_dbf_to_csv


class FakeField:
    def __init__(self, name):
        self.name = name


class FakeDBFTable:
    def __init__(self, rows, fields):
        self._rows = rows
        self.fields = [FakeField(name) for name in fields]

    def __iter__(self):
        return iter(self._rows)


class DbfExportCsvTests(unittest.TestCase):
    def test_export_dbf_to_csv_uses_table_name_and_writes_csv(self):
        rows = [{"codigo": 1, "nombre": "A"}, {"codigo": 2, "nombre": "B"}]
        fake_table = FakeDBFTable(rows, ["codigo", "nombre"])

        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = str(Path(tmpdir) / "mi_tabla.dbf")
            output_dir = Path(tmpdir) / "outputs"

            with patch("app.services.utils.dbf_reader.os.path.exists", return_value=True), \
                 patch("app.services.utils.dbf_reader.DBF", return_value=fake_table):
                output_path = export_dbf_to_csv(source_path, output_dir=str(output_dir))

            self.assertTrue(Path(output_path).exists())
            self.assertEqual(Path(output_path).name, "mi_tabla.csv")
            with open(output_path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                rows_read = list(reader)
            self.assertEqual(rows_read, [{"codigo": "1", "nombre": "A"}, {"codigo": "2", "nombre": "B"}])


if __name__ == "__main__":
    unittest.main()
