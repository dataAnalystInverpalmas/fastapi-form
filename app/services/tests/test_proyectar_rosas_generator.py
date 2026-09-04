from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from app.services.etl_jobs.proyectar_rosas_generator import (
    _build_projection_summary,
    _load_arre_data,
    _load_curva_variedad_rosas,
    _load_dates,
    _load_proyecciones_data,
    generate_proyectar_rosas_report,
    proyectar_tallos,
)


class ProyectarRosasGeneratorDbTests(unittest.TestCase):
    @patch("app.services.etl_jobs.proyectar_rosas_generator.db_connection")
    def test_load_sources_from_db(self, db_connection_mock):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchall.side_effect = [
            [(datetime(2024, 1, 1), 2024, 1), (datetime(2024, 1, 8), 2024, 2)],
            [
                (datetime(2024, 1, 1), "001", "ROSA1", 1, 100, "RE"),
            ],
            [
                (datetime(2024, 1, 1), "001", "ROSA1", 1, 20, "Poda"),
                (datetime(2024, 1, 1), "001", "ROSA1", 2, 30, "Poda"),
            ],
            [
                ("ROSA1", 1, json.dumps([0.5, 0.5]), json.dumps([1.0, 0.0]), json.dumps([0.0, 1.0]), json.dumps([1.0, 0.0])),
            ],
        ]
        db_connection_mock.return_value.__enter__.return_value = connection

        df_dates = _load_dates()
        df_proyecciones = _load_proyecciones_data()
        df_arre = _load_arre_data()
        df_varieties = _load_curva_variedad_rosas()

        self.assertEqual(list(df_dates.columns), ["fecha", "ano", "semana"])
        self.assertEqual(len(df_proyecciones), 1)
        self.assertEqual(df_proyecciones["tipo"].unique().tolist(), ["RE"])
        self.assertEqual(len(df_arre), 2)
        self.assertEqual(df_varieties.loc[0, "variedad"], "ROSA1")
        self.assertEqual(df_varieties.loc[0, "curva_distribucion"], [0.5, 0.5])

    @patch("app.services.etl_jobs.proyectar_rosas_generator.db_connection")
    def test_generate_report_builds_projection_dataframe(self, db_connection_mock):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchall.side_effect = [
            [
                (datetime(2024, 1, 1), "001", "ROSA1", 1, 100, "RE"),
                (datetime(2024, 1, 8), "001", "ROSA1", 1, 80, "RE"),
                (datetime(2024, 1, 1), "001", "ROSA1", 1, 60, "AJ"),
            ],
            [
                (datetime(2024, 1, 1), "001", "ROSA1", 1, 20, "Poda"),
                (datetime(2024, 1, 8), "001", "ROSA1", 1, 30, "Poda"),
            ],
            [
                ("ROSA1", 1, json.dumps([0.5, 0.5]), json.dumps([1.0, 0.0]), json.dumps([0.0, 1.0]), json.dumps([1.0, 0.0])),
            ],
        ]
        db_connection_mock.return_value.__enter__.return_value = connection

        output_path = generate_proyectar_rosas_report(
            fecha_inicio="2024-01-01",
            fecha_fin="2024-01-31",
        )

        self.assertTrue(output_path.endswith(".csv"))

    @patch("app.services.etl_jobs.proyectar_rosas_generator.db_connection")
    def test_generate_report_accepts_etl_params_dict(self, db_connection_mock):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchall.side_effect = [
            [
                (datetime(2024, 1, 1), "001", "ROSA1", 1, 100, "RE"),
            ],
            [
                (datetime(2024, 1, 1), "001", "ROSA1", 1, 20, "Poda"),
            ],
            [
                ("ROSA1", 1, json.dumps([0.5, 0.5]), json.dumps([1.0, 0.0]), json.dumps([0.0, 1.0]), json.dumps([1.0, 0.0])),
            ],
        ]
        db_connection_mock.return_value.__enter__.return_value = connection

        output_path = generate_proyectar_rosas_report({
            "fecha_inicio": "2024-01-01",
            "fecha_fin": "2024-01-31",
        })

        self.assertTrue(output_path.endswith(".csv"))

    @patch("app.services.etl_jobs.proyectar_rosas_generator.db_connection")
    def test_generate_report_writes_all_csv_outputs(self, db_connection_mock):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchall.side_effect = [
            [
                (datetime(2024, 1, 1), "001", "ROSA1", 1, 100, "RE"),
                (datetime(2024, 1, 8), "001", "ROSA1", 1, 80, "RE"),
            ],
            [
                (datetime(2024, 1, 1), "001", "ROSA1", 1, 20, "Poda"),
                (datetime(2024, 1, 8), "001", "ROSA1", 1, 30, "Poda"),
            ],
            [
                ("ROSA1", 1, json.dumps([0.5, 0.5]), json.dumps([1.0, 0.0]), json.dumps([0.0, 1.0]), json.dumps([1.0, 0.0])),
            ],
        ]
        db_connection_mock.return_value.__enter__.return_value = connection

        output_dir = Path(tempfile.mkdtemp())
        with patch("app.services.etl_jobs.proyectar_rosas_generator._resolve_output_dir", return_value=output_dir):
            output_path = generate_proyectar_rosas_report(
                fecha_inicio="2024-01-01",
                fecha_fin="2024-01-31",
            )

        self.assertTrue(Path(output_path).exists())
        self.assertTrue((output_dir / "proyeccion_rosas.csv").exists())
        self.assertTrue((output_dir / "arreglos.csv").exists())
        self.assertTrue((output_dir / "cortes.csv").exists())

    @patch("app.services.etl_jobs.proyectar_rosas_generator.db_connection")
    def test_load_proyecciones_data_ignores_aj(self, db_connection_mock):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchall.side_effect = [
            [
                (datetime(2024, 1, 1), "001", "ROSA1", 1, 100, "RE"),
                (datetime(2024, 1, 1), "001", "ROSA1", 1, 50, "AJ"),
            ],
        ]
        db_connection_mock.return_value.__enter__.return_value = connection

        df_proyecciones = _load_proyecciones_data()

        self.assertEqual(len(df_proyecciones), 1)
        self.assertEqual(df_proyecciones["tipo"].unique().tolist(), ["RE"])

    def test_projection_uses_curve_per_row_and_preserves_finca(self):
        df_operaciones = pd.DataFrame([
            {
                "fecha": pd.Timestamp("2024-01-01"),
                "finca": "001",
                "variedad": "ROSA1",
                "bloque": 1,
                "tallos": 100,
                "tipo": "RE",
            }
        ])
        df_varieties = pd.DataFrame([
            {
                "variedad": "ROSA1",
                "ciclo": 11,
                "curva_distribucion": [0.5, 0.5],
                "S1": [1.0, 0.0],
                "S2": [0.5, 0.5],
                "S3": [1.0, 0.0],
            }
        ])

        projected = proyectar_tallos(
            df_operaciones,
            df_varieties,
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-12-31"),
        )

        self.assertIn("finca", projected.columns)
        self.assertEqual(projected["finca"].unique().tolist(), ["001"])
        self.assertTrue(len(projected) >= 2)
        self.assertTrue(projected["tallos"].sum() > 0)

    def test_projection_spans_multiple_future_dates(self):
        df_hist = pd.DataFrame(
            [
                {"fecha": pd.Timestamp("2024-01-01"), "variedad": "ROSA1", "bloque": 1, "tallos": 100, "tipo": "Poda"},
                {"fecha": pd.Timestamp("2024-01-08"), "variedad": "ROSA1", "bloque": 1, "tallos": 120, "tipo": "Poda"},
                {"fecha": pd.Timestamp("2024-01-15"), "variedad": "ROSA1", "bloque": 1, "tallos": 140, "tipo": "Poda"},
            ]
        )
        df_varieties = pd.DataFrame([
            {"variedad": "ROSA1", "curva_distribucion": [0.2, 0.3, 0.5]},
        ])

        projected = _build_projection_summary(
            df_hist,
            df_varieties,
            "Poda",
            "2024-01-01",
            "2024-01-31",
        )

        self.assertGreater(len(projected), 1)
        self.assertTrue(projected["fecha_proyeccion"].nunique() > 1)

    def test_projection_orders_by_date_before_generating_future_rows(self):
        df_operaciones = pd.DataFrame([
            {
                "fecha": pd.Timestamp("2024-01-15"),
                "finca": "001",
                "variedad": "ROSA1",
                "bloque": 1,
                "tallos": 200,
                "tipo": "RE",
            },
            {
                "fecha": pd.Timestamp("2024-01-01"),
                "finca": "001",
                "variedad": "ROSA1",
                "bloque": 1,
                "tallos": 100,
                "tipo": "RE",
            },
        ])
        df_varieties = pd.DataFrame([
            {
                "variedad": "ROSA1",
                "ciclo": 12,
                "curva_distribucion": [0.2, 0.3, 0.5],
                "S1": [0.0, 0.0, 0.0],
                "S2": [0.0, 0.0, 0.0],
                "S3": [0.0, 0.0, 0.0],
            }
        ])

        projected = proyectar_tallos(
            df_operaciones,
            df_varieties,
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-12-31"),
        )

        self.assertTrue(projected["fecha"].tolist() == sorted(projected["fecha"].tolist()))
        self.assertEqual(projected["fecha"].min(), pd.Timestamp("2024-02-29"))


if __name__ == "__main__":
    unittest.main()
