import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app.core.settings import settings
from app.services.etl_jobs.quipus_vs_proy_generator import (
    _build_quipus_export,
    _load_plano_data,
    _load_quipus_data,
    _notify_cumplimiento_khipus,
)


class QuipusVsProySchemaTests(unittest.TestCase):
    def test_load_plano_data_accepts_programada_arranque_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "tika-plano-siembra-prueba.csv")
            pd.DataFrame(
                [{
                    "Finca": "001",
                    "Bloque": "10",
                    "Variedad": "Rosa",
                    "Flor": "CLA",
                    "Estado": "Sembrada",
                    "Semana": 2501,
                    "S. arranque programada": 2515,
                    "S. arranque real": 2516,
                    "Fiesta (pico)": "2025",
                    "Esquejes sembrados": 120,
                }]
            ).to_csv(csv_path, index=False)

            original_path = settings.QUIPUS_PLANO_PATH
            settings.QUIPUS_PLANO_PATH = csv_path
            try:
                df_plano_group_s, df_plano_group_a, df_plano_final, df_nplantas = _load_plano_data(2500)
            finally:
                settings.QUIPUS_PLANO_PATH = original_path

        self.assertFalse(df_plano_group_s.empty)
        self.assertIn("farranque", df_plano_group_s.columns)
        self.assertFalse(df_nplantas.empty)
        self.assertEqual(df_nplantas.iloc[0]["cosecha"], "2025")

    def test_load_quipus_data_accepts_proyeccion_khipus_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pd.DataFrame(
                [{
                    "Finca": "001",
                    "Variedad": "Rosa",
                    "Color": "Rojo",
                    "Flor": "CLA",
                    "Estado": "Sembrada",
                    "Semana de siembra": 2501,
                    "Semana de producción": 2510,
                    "Bloque": "10",
                    "Edad": 9,
                    "Proyección khipus": 150,
                }]
            ).to_csv(os.path.join(tmpdir, "tika-quipus2640.csv"), index=False)

            original_dir = settings.QUIPUS_TIKA_DIR
            original_prefix = settings.QUIPUS_TIKA_FILE_PREFIX
            settings.QUIPUS_TIKA_DIR = tmpdir
            settings.QUIPUS_TIKA_FILE_PREFIX = "tika-quipus"
            try:
                df_quipus = _load_quipus_data(2640)
            finally:
                settings.QUIPUS_TIKA_DIR = original_dir
                settings.QUIPUS_TIKA_FILE_PREFIX = original_prefix

        self.assertIn("cantidad", df_quipus.columns)
        self.assertEqual(int(df_quipus["cantidad"].sum()), 150)


class QuipusExportTests(unittest.TestCase):
    def _quipus_row(self, variedad: str) -> dict:
        return {
            "finca": "001",
            "flor": "CLA",
            "bloque": "10",
            "cosecha": "2025",
            "variedad": variedad,
            "sem_prod": 2601,
            "cantidad": 100,
            "tipo": "proyección",
            "fuente": "quipus",
            "nfiesta": "25",
        }

    def test_build_quipus_export_agrega_codigo_y_nombre_con_espacios(self) -> None:
        df_quipus = pd.DataFrame([self._quipus_row("SUPER_KING")])
        df_codigos = pd.DataFrame([{"codigo": "12", "nombre": "SUPER KING"}])

        out = _build_quipus_export(df_quipus, df_codigos)

        self.assertIn("codigo", out.columns)
        self.assertEqual(len(out), 1)
        self.assertEqual(out.iloc[0]["codigo"], "12")
        self.assertEqual(out.iloc[0]["variedad"], "SUPER KING")
        self.assertNotIn("variedad_nombre", out.columns)

    def test_build_quipus_export_descarta_variedades_sin_codigo(self) -> None:
        df_quipus = pd.DataFrame([self._quipus_row("SUPER_KING")])
        df_codigos = pd.DataFrame([{"codigo": "12", "nombre": "OTRA_VARIEDAD"}])

        out = _build_quipus_export(df_quipus, df_codigos)

        self.assertTrue(out.empty)


class CumplimientoEmailTests(unittest.TestCase):
    def _notify(self, excel_path: Path, semana: int, mock_send) -> None:
        with patch(
            "app.services.etl_jobs.quipus_vs_proy_generator.settings.QUIPUS_CUMPLIMIENTO_EMAILS",
            ["estadistica@inverpalmas.com"],
        ), patch("app.services.etl_jobs.quipus_vs_proy_generator.send_email", mock_send):
            _notify_cumplimiento_khipus(excel_path=excel_path, row_count=3, enviar_email=True, semana=semana)

    def test_sends_only_once_per_week(self) -> None:
        from unittest.mock import MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            excel_path = Path(tmpdir) / "cumplimiento_khipus_10_semanas.xlsx"
            excel_path.write_bytes(b"")
            mock_send = MagicMock()

            self._notify(excel_path, 2640, mock_send)
            # Segunda corrida del paso 1 en la misma semana (tras subir ajustes a Tika).
            self._notify(excel_path, 2640, mock_send)
            self.assertEqual(mock_send.call_count, 1)

            self._notify(excel_path, 2641, mock_send)
            self.assertEqual(mock_send.call_count, 2)

    def test_failed_send_does_not_mark_week_as_sent(self) -> None:
        from unittest.mock import MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            excel_path = Path(tmpdir) / "cumplimiento_khipus_10_semanas.xlsx"
            excel_path.write_bytes(b"")

            self._notify(excel_path, 2640, MagicMock(side_effect=RuntimeError("smtp caido")))
            mock_send = MagicMock()
            self._notify(excel_path, 2640, mock_send)
            mock_send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
