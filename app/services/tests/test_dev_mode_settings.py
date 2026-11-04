"""Modo desarrollo: DEV_OUTPUT_DIR redirige todas las salidas (ver Settings)."""
from __future__ import annotations

import os
import unittest
from collections import Counter
from unittest import mock

from app.core.settings import Settings

DEV_DIR = r"\\172.10.18.2\Usuarios\Outputs_dev"


def _dev_settings(**kwargs) -> Settings:
    return Settings(_env_file=None, DEV_OUTPUT_DIR=DEV_DIR, **kwargs)


class DevOutputRedirectTests(unittest.TestCase):
    def test_sin_dev_output_dir_no_cambia_nada(self):
        prod = Settings(_env_file=None, DEV_OUTPUT_DIR="")
        default = Settings.model_fields["PROCESS_SIEMBRAS_OUTPUT_PATH"].default
        self.assertEqual(prod.PROCESS_SIEMBRAS_OUTPUT_PATH, default)

    def test_archivos_y_carpetas_van_a_dev(self):
        s = _dev_settings()
        self.assertEqual(s.PROCESS_SIEMBRAS_OUTPUT_PATH, DEV_DIR + r"\plano nuevo siembra.xlsx")
        self.assertEqual(s.EXCEL_OUTPUT_DIR, DEV_DIR)
        # Ruta con barras normales en settings y salida sin OUTPUT en el nombre.
        self.assertEqual(s.QUIPUS_OUTPUT_PATH, DEV_DIR + r"\quipus.csv")
        self.assertEqual(s.DIRIGIDAS_RESUMEN_PATH, DEV_DIR + r"\dirigidas_resumen.xlsx")

    def test_ninguna_salida_queda_fuera_de_dev(self):
        s = _dev_settings()
        for name in Settings.output_setting_names():
            value = getattr(s, name)
            if value:
                self.assertTrue(value.startswith(DEV_DIR), f"{name} = {value}")

    def test_entradas_no_cambian(self):
        s = _dev_settings()
        self.assertEqual(s.LOAD_LD_BCULT_DIR, Settings.model_fields["LOAD_LD_BCULT_DIR"].default)
        self.assertEqual(s.PICOS_DEMANDA_PATH, Settings.model_fields["PICOS_DEMANDA_PATH"].default)

    def test_dos_salidas_no_comparten_archivo_en_dev(self):
        s = _dev_settings()
        files = [
            getattr(s, n).lower()
            for n in Settings.output_setting_names()
            if not n.endswith("_DIR") and getattr(s, n)
        ]
        repetidos = [path for path, count in Counter(files).items() if count > 1]
        self.assertEqual(repetidos, [])

    def test_override_de_config_tambien_se_redirige(self):
        s = _dev_settings()
        applied = s.apply_overrides({"PROCESS_SIEMBRAS_OUTPUT_PATH": r"\\172.10.18.2\usuarios\x\otro.xlsx"})
        self.assertEqual(s.PROCESS_SIEMBRAS_OUTPUT_PATH, DEV_DIR + r"\otro.xlsx")
        # /config persiste lo que se pidio, no la ruta de desarrollo.
        self.assertEqual(applied["PROCESS_SIEMBRAS_OUTPUT_PATH"], r"\\172.10.18.2\usuarios\x\otro.xlsx")

    def test_reset_conserva_modo_desarrollo(self):
        s = _dev_settings()
        s.reset_to_defaults()
        self.assertEqual(s.DEV_OUTPUT_DIR, DEV_DIR)
        self.assertEqual(s.PROCESS_SIEMBRAS_OUTPUT_PATH, DEV_DIR + r"\plano nuevo siembra.xlsx")

    def test_dev_dir_con_barras_normales(self):
        s = Settings(_env_file=None, DEV_OUTPUT_DIR="//172.10.18.2/Usuarios/Outputs_dev/")
        self.assertEqual(s.PROCESS_SIEMBRAS_OUTPUT_PATH, "//172.10.18.2/Usuarios/Outputs_dev/plano nuevo siembra.xlsx")

    def test_scheduler_se_apaga_por_entorno(self):
        with mock.patch.dict(os.environ, {"SCHEDULER_ENABLED": "false"}):
            self.assertFalse(Settings(_env_file=None).SCHEDULER_ENABLED)
        self.assertTrue(Settings(_env_file=None).SCHEDULER_ENABLED)


if __name__ == "__main__":
    unittest.main()
