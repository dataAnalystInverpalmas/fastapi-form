import unittest

from app.core.config_store import _CONFIG_FILE, get_config_overrides, save_config_overrides, get_setting_groups
from app.core.settings import settings
from app.services.etl.params import normalize_job_params


class EtlParamsTests(unittest.TestCase):
    def test_normalize_curve_paths_accepts_newlines(self) -> None:
        params = normalize_job_params(
            "resumir_curvas_usadas",
            {
                "curve_paths": "//svrinverpalmas/usuarios/Hilder/Data/tika-curvas2026v2.csv\n//svrinverpalmas/usuarios/Hilder/Data/tika-curvas2027v2.csv",
                "curve_years": "2026, 2027",
            },
        )

        self.assertEqual(
            params["curve_paths"],
            [
                "//svrinverpalmas/usuarios/Hilder/Data/tika-curvas2026v2.csv",
                "//svrinverpalmas/usuarios/Hilder/Data/tika-curvas2027v2.csv",
            ],
        )
        self.assertEqual(params["curve_years"], [2026, 2027])

    def test_normalize_final_filter_value_as_int(self) -> None:
        params = normalize_job_params(
            "resumir_curvas_usadas",
            {
                "final_filter_value": "1",
            },
        )

        self.assertEqual(params["final_filter_value"], 1)

    def test_normalize_curve_paths_from_list_with_joined_csv_strings(self) -> None:
        params = normalize_job_params(
            "resumir_curvas_usadas",
            {
                "curve_paths": [
                    "//svrinverpalmas/usuarios/Hilder/Data/tika-curvas2026v2.csv, //svrinverpalmas/usuarios/Hilder/Data/tika-curvas2027v3.csv"
                ],
                "curve_years": [2026, 2027],
            },
        )

        self.assertEqual(
            params["curve_paths"],
            [
                "//svrinverpalmas/usuarios/Hilder/Data/tika-curvas2026v2.csv",
                "//svrinverpalmas/usuarios/Hilder/Data/tika-curvas2027v3.csv",
            ],
        )
        self.assertEqual(params["curve_years"], [2026, 2027])

    def test_settings_overrides_can_be_grouped_and_saved(self) -> None:
        # Respalda el archivo REAL .app_config_overrides.json (no un fixture)
        # byte a byte: save_config_overrides fusiona con lo existente, asi
        # que guardar el "original" de vuelta no alcanza para deshacer un
        # DB_HOST de prueba -- eso dejo corriendo con host falso cualquier
        # servidor real que arranque despues de correr esta suite.
        file_existed = _CONFIG_FILE.exists()
        file_backup = _CONFIG_FILE.read_text(encoding="utf-8") if file_existed else None
        overrides_backup = dict(get_config_overrides())
        try:
            groups = get_setting_groups()

            self.assertIn("app", groups)
            self.assertTrue(any(key in groups["app"] for key in ["APP_NAME", "APP_VERSION", "DEBUG", "APP_ENV"]))
            self.assertIn("db", groups)
            self.assertTrue(any(key in groups["db"] for key in ["DB_HOST", "DB_PORT", "DB_NAME"]))

            save_config_overrides({"APP_NAME": "Portal Demo", "DB_HOST": "db.test.local"})
            self.assertEqual(get_config_overrides()["APP_NAME"], "Portal Demo")
            self.assertEqual(get_config_overrides()["DB_HOST"], "db.test.local")
        finally:
            if file_existed:
                _CONFIG_FILE.write_text(file_backup, encoding="utf-8")
            elif _CONFIG_FILE.exists():
                _CONFIG_FILE.unlink()
            settings.reset_to_defaults()
            settings.apply_overrides(overrides_backup, strict=False)

    def test_list_setting_value_is_coerced_without_recursing(self) -> None:
        from app.core.settings import settings

        result = settings._coerce_value("COMPARE_TIKA_DEFAULT_MODELS", "161, 328, 485, 405")

        self.assertEqual(result, [161, 328, 485, 405])


if __name__ == "__main__":
    unittest.main()