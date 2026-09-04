import unittest

from app.core.config_store import get_config_overrides, save_config_overrides, get_setting_groups
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
        original = get_config_overrides()
        groups = get_setting_groups()

        self.assertIn("app", groups)
        self.assertTrue(any(key in groups["app"] for key in ["APP_NAME", "APP_VERSION", "DEBUG", "APP_ENV"]))
        self.assertIn("db", groups)
        self.assertTrue(any(key in groups["db"] for key in ["DB_HOST", "DB_PORT", "DB_NAME"]))

        save_config_overrides({"APP_NAME": "Portal Demo", "DB_HOST": "db.test.local"})
        self.assertEqual(get_config_overrides()["APP_NAME"], "Portal Demo")
        self.assertEqual(get_config_overrides()["DB_HOST"], "db.test.local")

        save_config_overrides(original)

    def test_list_setting_value_is_coerced_without_recursing(self) -> None:
        from app.core.settings import settings

        result = settings._coerce_value("COMPARE_TIKA_DEFAULT_MODELS", "161, 328, 485, 405")

        self.assertEqual(result, [161, 328, 485, 405])


if __name__ == "__main__":
    unittest.main()