import unittest

from app.core.config_store import _CONFIG_FILE, get_config_overrides, get_setting_groups
from app.core.settings import Settings, settings
from app.routes.config import list_config_values, save_config, reset_config


class SettingGroupsTests(unittest.TestCase):
    """Todo campo de Settings debe caer en exactamente un grupo, para que la
    pantalla de configuracion (/config, Vue) los muestre todos sin
    duplicados ni huerfanos."""

    def test_every_field_is_grouped_exactly_once(self) -> None:
        groups = get_setting_groups()
        all_keys = [key for keys in groups.values() for key in keys]

        self.assertEqual(len(all_keys), len(set(all_keys)), "hay campos duplicados entre grupos")
        self.assertEqual(set(all_keys), set(Settings.model_fields.keys()))

    def test_new_prefixes_land_in_dedicated_groups_not_general(self) -> None:
        groups = get_setting_groups()
        self.assertIn("BAJAS_EXPORTADO_EXPORTADO_PATH", groups["bajas_exportado"])
        self.assertIn("CORTES_LONAS_FLOR_FILTER", groups["cortes_lonas"])
        self.assertIn("INFORMES_JEFES_AREA_MES_ACUMULA", groups["informes_jefes_de_area"])
        self.assertIn("QUALITIES_PIPELINE_NAL_APORTE_MAX", groups["calidades"])


class ApplyOverridesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original = settings.ALL_FARMS_CODE

    def tearDown(self) -> None:
        settings.ALL_FARMS_CODE = self._original

    def test_strict_mode_rejects_unknown_key(self) -> None:
        with self.assertRaises(ValueError):
            settings.apply_overrides({"CAMPO_QUE_NO_EXISTE": "x"})

    def test_lenient_mode_skips_unknown_key_instead_of_raising(self) -> None:
        applied = settings.apply_overrides({"CAMPO_QUE_NO_EXISTE": "x"}, strict=False)
        self.assertEqual(applied, {})

    def test_dict_field_roundtrips_through_json_string(self) -> None:
        applied = settings.apply_overrides({
            "PEDIDOS_SURTIDO_FLOR_MAP": '{"CLA": "CLAVEL_TEST"}',
        })
        self.assertEqual(applied["PEDIDOS_SURTIDO_FLOR_MAP"], {"CLA": "CLAVEL_TEST"})
        self.assertEqual(settings.PEDIDOS_SURTIDO_FLOR_MAP, {"CLA": "CLAVEL_TEST"})
        # restaurar
        settings.apply_overrides({
            "PEDIDOS_SURTIDO_FLOR_MAP": '{"CLA": "CLAVEL", "CM0": "MINI"}',
        })

    def test_list_field_roundtrips_through_comma_string(self) -> None:
        applied = settings.apply_overrides({"CORTES_LONAS_FLOR_FILTER": "CLA, CM0, ROS"})
        self.assertEqual(applied["CORTES_LONAS_FLOR_FILTER"], ["CLA", "CM0", "ROS"])
        settings.apply_overrides({"CORTES_LONAS_FLOR_FILTER": "CLA, CM0"})


class ConfigApiTests(unittest.TestCase):
    """La pantalla de administracion (frontend/src/views/ConfigView.vue)
    consume estos endpoints directamente (sin Jinja); se prueban las
    funciones de la ruta tal cual las llama FastAPI.

    Estas pruebas escriben/borran .app_config_overrides.json (un archivo
    real del repo, no un fixture), asi que cada test respalda su contenido
    exacto y lo restaura al final -- incluidos los overrides legitimos que
    alguien ya haya guardado desde la UI (ej. COMPARE_TIKA_DEMANDA_PATH)."""

    def setUp(self) -> None:
        self._file_existed = _CONFIG_FILE.exists()
        self._file_backup = _CONFIG_FILE.read_text(encoding="utf-8") if self._file_existed else None
        self._overrides_backup = dict(get_config_overrides())

    def tearDown(self) -> None:
        if self._file_existed:
            _CONFIG_FILE.write_text(self._file_backup, encoding="utf-8")
        elif _CONFIG_FILE.exists():
            _CONFIG_FILE.unlink()

        settings.reset_to_defaults()
        settings.apply_overrides(self._overrides_backup, strict=False)

    def test_values_endpoint_returns_groups_values_defaults_and_overrides(self) -> None:
        payload = list_config_values()
        self.assertIn("groups", payload)
        self.assertIn("values", payload)
        self.assertIn("defaults", payload)
        self.assertIn("overrides", payload)

        self.assertIn("informes_jefes_de_area", payload["groups"])
        self.assertIn("bajas_exportado", payload["groups"])

        # un valor dict debe llegar completo (no solo sus llaves) para que la
        # UI lo pueda mostrar como JSON editable.
        self.assertEqual(
            payload["values"]["PEDIDOS_SURTIDO_FLOR_MAP"],
            {"CLA": "CLAVEL", "CM0": "MINI"},
        )

    def test_save_merges_with_existing_overrides_instead_of_replacing(self) -> None:
        # simula un override ya guardado por otro grupo/formulario
        save_config({"DIRIGIDAS_CAMAS_MIN": "7"})
        # guardar un campo de OTRO grupo no debe borrar el anterior
        save_config({"CORTES_LONAS_FLOR_FILTER": "CLA, CM0, ROS"})

        overrides = get_config_overrides()
        self.assertEqual(overrides["DIRIGIDAS_CAMAS_MIN"], 7)
        self.assertEqual(overrides["CORTES_LONAS_FLOR_FILTER"], ["CLA", "CM0", "ROS"])

    def test_save_then_reset_roundtrip(self) -> None:
        save_config({"DIRIGIDAS_CAMAS_MIN": "7"})

        payload = list_config_values()
        self.assertEqual(payload["values"]["DIRIGIDAS_CAMAS_MIN"], 7)
        self.assertEqual(payload["overrides"]["DIRIGIDAS_CAMAS_MIN"], 7)

        reset_config()

        payload = list_config_values()
        self.assertEqual(payload["values"]["DIRIGIDAS_CAMAS_MIN"], 4)
        self.assertNotIn("DIRIGIDAS_CAMAS_MIN", payload["overrides"])

    def test_save_rejects_unknown_field_with_422_style_error(self) -> None:
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            save_config({"CAMPO_INVENTADO": "x"})
        self.assertEqual(ctx.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
