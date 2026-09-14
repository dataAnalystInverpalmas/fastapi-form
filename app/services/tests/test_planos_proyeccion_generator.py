import unittest
from pathlib import Path
from unittest.mock import patch

import mysql.connector
import pandas as pd

from app.services.etl_jobs.planos_proyeccion_generator import (
    SOURCE_COLUMNS,
    _attach_id_lote_siembra,
    _build_ajustes_export,
    _build_finca_email_body,
    _build_hoja2_export,
    _build_tika_upload_body,
    _fill_tika_workbook,
    _load_base_from_staging,
    _notify_ajustes_por_finca,
    _notify_tika_ajuste,
    _transform_base_sheet,
    _transform_lotes_siembra,
)


class PlanosProyeccionGeneratorTests(unittest.TestCase):
    def _build_raw(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "finca": [2.0, 2.0, None],
                "bloque": [1.0, 3.0, 1.0],
                "variedad": ["2048", "2149", "2048"],
                "cosecha": ["SE2638", "JL2631", "SE2638"],
                "nvari": ["FARIDA", "MOON LIGHT", "FARIDA"],
                "fec_siem": pd.to_datetime(["2026-03-11", "2026-01-21", "2026-03-11"]),
                "rev": [0.0, 0.0, 0.0],
                "amort": [1.0, 1.0, 1.0],
                "proyecta_quipus": [0.88, 1.17, 0.88],
                "edad": [26, 33, 26],
            }
        )

    def test_transform_extracts_and_normalizes_expected_columns(self) -> None:
        df, audit = _transform_base_sheet(self._build_raw())

        self.assertEqual(list(df.columns), [
            "finca", "bloque", "variedad", "cosecha", "nvari", "yyww_siembra", "rev", "amort", "proyecta_quipus",
        ])
        self.assertEqual(len(df), 2)
        self.assertEqual(audit["raw_rows"], 3)
        self.assertEqual(audit["rows_after_dropna_finca"], 2)
        self.assertEqual(audit["final_rows"], 2)

        row = df.iloc[0]
        self.assertEqual(row["finca"], "002")
        self.assertEqual(row["bloque"], "1")
        self.assertEqual(row["variedad"], "2048")
        self.assertEqual(row["nvari"], "FARIDA")
        self.assertEqual(row["yyww_siembra"], "2611")

    def test_transform_replaces_spaces_in_nvari_with_underscore(self) -> None:
        df, _audit = _transform_base_sheet(self._build_raw())
        self.assertEqual(df.iloc[1]["nvari"], "MOON_LIGHT")

    def test_transform_raises_when_required_column_missing(self) -> None:
        df_raw = self._build_raw().drop(columns=["proyecta_quipus"])
        with self.assertRaises(ValueError):
            _transform_base_sheet(df_raw)

    def test_transform_keeps_variedad_as_text_without_numeric_coercion(self) -> None:
        df_raw = self._build_raw()
        df_raw["variedad"] = ["A048", "2149", "2048"]

        df, _audit = _transform_base_sheet(df_raw)

        self.assertEqual(df.iloc[0]["variedad"], "A048")
        self.assertEqual(df.iloc[1]["variedad"], "2149")

    def test_transform_parses_fec_siem_stored_as_excel_serial_number(self) -> None:
        df_raw = self._build_raw()
        df_raw["fec_siem"] = [45807, "2026-01-21", "2026-03-11"]

        df, audit = _transform_base_sheet(df_raw)

        self.assertEqual(audit["invalid_fec_siem_rows"], 0)
        self.assertEqual(df.iloc[0]["yyww_siembra"], "2522")

    def test_palermo_and_palmas_frames_combine_with_both_fincas(self) -> None:
        df_palermo, _ = _transform_base_sheet(self._build_raw())

        df_palmas_raw = self._build_raw().assign(finca=[1.0, 1.0, None])
        df_palmas, _ = _transform_base_sheet(df_palmas_raw)

        combined = pd.concat([df_palermo, df_palmas], ignore_index=True)

        self.assertEqual(len(combined), 4)
        self.assertEqual(set(combined["finca"]), {"001", "002"})

    def _build_raw_lotes(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "Id": [12695, 12670, 99999],
                "Finca": ["PALERMO", "PALERMO", "INVERPALMAS"],
                "Bloque": [1, 1, 5],
                "Variedad": ["FARIDA", "DON PEDRO", "OTRA"],
                "Semana de siembra": [2611, 2610, 2601],
            }
        )

    def test_transform_lotes_siembra_normalizes_join_keys(self) -> None:
        df = _transform_lotes_siembra(self._build_raw_lotes())

        self.assertEqual(list(df.columns), ["finca", "bloque", "nvari", "yyww_siembra", "id_lote_siembra"])
        row = df.iloc[0]
        self.assertEqual(row["finca"], "002")
        self.assertEqual(row["bloque"], "1")
        self.assertEqual(row["nvari"], "FARIDA")
        self.assertEqual(row["yyww_siembra"], "2611")
        self.assertEqual(row["id_lote_siembra"], 12695)

    def test_transform_lotes_siembra_raises_when_column_missing(self) -> None:
        df_raw = self._build_raw_lotes().drop(columns=["Semana de siembra"])
        with self.assertRaises(ValueError):
            _transform_lotes_siembra(df_raw)

    def test_attach_id_lote_siembra_matches_on_finca_bloque_nvari_semana(self) -> None:
        df_planos, _ = _transform_base_sheet(self._build_raw())
        df_lotes = _transform_lotes_siembra(self._build_raw_lotes())

        result = _attach_id_lote_siembra(df_planos, df_lotes)

        self.assertIn("id_lote_siembra", result.columns)
        self.assertEqual(len(result), len(df_planos))
        matched = result[result["nvari"] == "FARIDA"]
        self.assertEqual(matched.iloc[0]["id_lote_siembra"], 12695)

    def test_attach_id_lote_siembra_leaves_null_when_no_match(self) -> None:
        df_planos, _ = _transform_base_sheet(self._build_raw())
        df_lotes = _transform_lotes_siembra(self._build_raw_lotes()).iloc[0:0]

        result = _attach_id_lote_siembra(df_planos, df_lotes)
        self.assertTrue(result["id_lote_siembra"].isna().all())

    def test_attach_id_lote_siembra_does_not_duplicate_rows_on_ambiguous_key(self) -> None:
        df_planos, _ = _transform_base_sheet(self._build_raw())
        df_lotes = pd.concat(
            [
                _transform_lotes_siembra(self._build_raw_lotes()),
                _transform_lotes_siembra(self._build_raw_lotes().assign(Id=[1, 2, 3])),
            ],
            ignore_index=True,
        )

        result = _attach_id_lote_siembra(df_planos, df_lotes)
        self.assertEqual(len(result), len(df_planos))

    def _build_matched(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "finca": ["002", "002", "001", "001"],
                "bloque": ["1", "1", "5", "5"],
                "variedad": ["2048", "2149", "2308", "2431"],
                "cosecha": ["SE2638", "JL2631", "AB2616", "JL2629"],
                "nvari": ["FARIDA", "MOON_LIGHT", "NOVIA", "UKELELE"],
                "yyww_siembra": ["2611", "2604", "2539", "2501"],
                # sin_cambios: Factor=1, Mueve semanas=0 -> se excluye (nada cambio).
                # solo_mueve_semanas: Factor=1, Mueve semanas!=0 -> se incluye (OR).
                # solo_factor: Factor!=1, Mueve semanas=0 -> se incluye (OR).
                # ambos_cambian: Factor!=1 y Mueve semanas!=0 -> se incluye.
                "rev": [0.0, 2.0, 0.0, -3.0],
                "amort": [1.0, 1.0, 0.5, 1.2],
                "proyecta_quipus": [1.0, 1.0, 1.0, 1.0],
                "id_lote_siembra": [111, 222, 333, 444],
            }
        )

    def test_build_ajustes_export_keeps_rows_where_either_factor_or_mueve_semanas_changed(self) -> None:
        result = _build_ajustes_export(self._build_matched())

        self.assertEqual(set(result["ID"]), {222, 333, 444})
        self.assertNotIn(111, set(result["ID"]))

    def test_build_ajustes_export_renames_and_adds_fixed_columns(self) -> None:
        result = _build_ajustes_export(self._build_matched())

        self.assertEqual(list(result.columns), ["finca", "ID", "Factor", "Mueve semanas", "Vigencia", "Bloqueado"])
        row = result[result["ID"] == 444].iloc[0]
        self.assertEqual(row["finca"], "001")
        self.assertEqual(row["Factor"], 1.2)
        self.assertEqual(row["Mueve semanas"], -3.0)
        self.assertEqual(row["Vigencia"], 10)
        self.assertEqual(row["Bloqueado"], 0)

    def test_build_ajustes_export_keeps_finca_for_filtering_but_not_in_excel_columns(self) -> None:
        result = _build_ajustes_export(self._build_matched())

        self.assertIn("finca", result.columns)
        excel_columns = [c for c in result.columns if c != "finca"]
        self.assertEqual(excel_columns, ["ID", "Factor", "Mueve semanas", "Vigencia", "Bloqueado"])

    def test_build_ajustes_export_nan_factor_does_not_falsely_qualify_unchanged_row(self) -> None:
        # id 111 no tiene cambios reales (Factor=1, Mueve semanas=0); si el
        # guard de notna() no funcionara, pandas evalua "NaN != 1" como True
        # y la fila se colaria por error.
        df = self._build_matched()
        df.loc[df["id_lote_siembra"] == 111, "amort"] = float("nan")

        result = _build_ajustes_export(df)

        self.assertNotIn(111, set(result["ID"]))

    def test_load_base_from_staging_returns_rows_for_finca(self) -> None:
        fake_rows = [("002", "1", "2048", "SE2638", "FARIDA", "2026-03-11", 0.0, 1.0, 0.88)]
        with patch(
            "app.services.etl_jobs.planos_proyeccion_generator.execute_query", return_value=fake_rows
        ) as mock_query:
            df = _load_base_from_staging("002")

        self.assertEqual(list(df.columns), SOURCE_COLUMNS)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["nvari"], "FARIDA")
        self.assertIn("finca = '002'", mock_query.call_args[0][0])
        self.assertIn("estado = 'activo'", mock_query.call_args[0][0])

    def test_load_base_from_staging_returns_empty_df_when_table_missing(self) -> None:
        error = mysql.connector.errors.ProgrammingError("Table 'informes.stg_plano_proyeccion' doesn't exist")
        error.errno = 1146
        with patch(
            "app.services.etl_jobs.planos_proyeccion_generator.execute_query", side_effect=error
        ):
            df = _load_base_from_staging("001")

        self.assertEqual(list(df.columns), SOURCE_COLUMNS)
        self.assertTrue(df.empty)

    def _build_missing(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "finca": ["001"],
                "bloque": ["34"],
                "variedad": ["2146"],
                "cosecha": ["JL2628"],
                "nvari": ["GOLEM"],
                "yyww_siembra": ["2501"],
            }
        )

    def test_build_finca_email_body_always_mentions_attachment(self) -> None:
        body = _build_finca_email_body("Palermo", pd.DataFrame(), ajustes_rows=5)
        self.assertIn("ajustes_proyeccion_palermo.xlsx", body)
        self.assertIn("5", body)
        self.assertNotIn("no cruzaron", body)

    def test_build_finca_email_body_includes_missing_table_when_present(self) -> None:
        body = _build_finca_email_body("Palmas", self._build_missing(), ajustes_rows=5)
        self.assertIn("no cruzaron", body)
        self.assertIn("GOLEM", body)

    def test_notify_ajustes_por_finca_skips_send_when_nothing_to_report(self) -> None:
        import tempfile

        df_ajustes = self._build_ajustes_for_notify()
        # Deja ambas fincas sin filas de ajuste y sin faltantes.
        df_ajustes = df_ajustes.iloc[0:0]
        df_missing = pd.DataFrame(columns=["finca", "bloque", "variedad", "cosecha", "nvari", "yyww_siembra"])

        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "app.services.etl_jobs.planos_proyeccion_generator.send_email"
        ) as mock_send:
            _notify_ajustes_por_finca(df_ajustes, df_missing, Path(tmp_dir))

        mock_send.assert_not_called()

    def _build_ajustes_for_notify(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "finca": ["002", "001"],
                "ID": [111, 222],
                "Factor": [1.2, 0.8],
                "Mueve semanas": [-3.0, 2.0],
                "Vigencia": [10, 10],
                "Bloqueado": [0, 0],
            }
        )

    def test_notify_ajustes_por_finca_sends_one_email_per_finca_with_its_own_file(self) -> None:
        import tempfile

        df_ajustes = self._build_ajustes_for_notify()
        df_missing = pd.DataFrame(columns=["finca", "bloque", "variedad", "cosecha", "nvari", "yyww_siembra"])

        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "app.services.etl_jobs.planos_proyeccion_generator.settings.PLANOS_PROYECCION_AJUSTES_EMAILS_PALERMO",
            ["estadistica@inverpalmas.com"],
        ), patch(
            "app.services.etl_jobs.planos_proyeccion_generator.settings.PLANOS_PROYECCION_AJUSTES_EMAILS_PALMAS",
            ["estadistica@inverpalmas.com"],
        ), patch(
            "app.services.etl_jobs.planos_proyeccion_generator.send_email"
        ) as mock_send:
            resultados = _notify_ajustes_por_finca(df_ajustes, df_missing, Path(tmp_dir))

            self.assertEqual(mock_send.call_count, 2)
            for call in mock_send.call_args_list:
                _, kwargs = call
                self.assertEqual(kwargs["to"], ["estadistica@inverpalmas.com"])
                self.assertEqual(len(kwargs["attachments"]), 1)
                self.assertTrue(kwargs["attachments"][0].exists())

        self.assertEqual(resultados["002"]["ajustes_rows"], 1)
        self.assertEqual(resultados["001"]["ajustes_rows"], 1)

    def test_build_hoja2_export_keeps_only_rows_with_real_adjustment(self) -> None:
        result = _build_hoja2_export(self._build_matched())

        self.assertEqual(list(result.columns), ["finca", "bloque", "variedad", "cosecha", "rev", "amort"])
        self.assertEqual(len(result), 3)
        self.assertEqual(set(result["variedad"]), {"2149", "2308", "2431"})

    def test_build_tika_upload_body_mentions_upload_url_steps_and_ajustes_files(self) -> None:
        body = _build_tika_upload_body(["ajustes_proyeccion_palermo.xlsx", "ajustes_proyeccion_palmas.xlsx"])
        self.assertIn("inverpalmas-tika.meliusid.app/khipus/projection_adjustments", body)
        self.assertIn("Curvas khipus", body)
        self.assertIn("Confinados", body)
        self.assertIn("ajustes_proyeccion_palermo.xlsx", body)
        self.assertIn("ajustes_proyeccion_palmas.xlsx", body)

    def _write_template(self, path: Path) -> None:
        import openpyxl

        wb = openpyxl.Workbook()
        hoja1 = wb.active
        hoja1.title = "Hoja1"
        hoja1.append(["tipo", "año", "semana", "finca", "flor", "bloque", "cosecha", "variedad", "tallos"])
        hoja1.append(["x", 2026, 1, "001", "ROS", "1", "EN2601", "2048", 100])

        hoja2 = wb.create_sheet("Hoja2")
        hoja2.append(["finca", "bloque", "variedad", "cosecha", "rev", "amort"])
        hoja2.append(["999", "99", "9999", "OLD9999", -9, 0.1])
        wb.save(path)

    def test_fill_tika_workbook_clears_hoja1_rows_and_writes_hoja2(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            template_path = Path(tmp_dir) / "template.xlsx"
            self._write_template(template_path)

            df_hoja2 = _build_hoja2_export(self._build_matched())
            output_path = Path(tmp_dir) / "output.xlsx"
            _fill_tika_workbook(df_hoja2, template_path, output_path)

            import openpyxl

            wb = openpyxl.load_workbook(output_path)
            self.assertEqual(wb["Hoja1"].max_row, 1)
            hoja2_rows = list(wb["Hoja2"].iter_rows(min_row=2, values_only=True))
            self.assertEqual(len(hoja2_rows), len(df_hoja2))
            self.assertNotIn("999", [row[0] for row in hoja2_rows])

    def _write_ajustes_files(self, tmp_dir: str) -> dict[str, dict[str, object]]:
        import openpyxl

        ajustes_files: dict[str, dict[str, object]] = {}
        for finca_code, finca_name in (("002", "palermo"), ("001", "palmas")):
            path = Path(tmp_dir) / f"ajustes_proyeccion_{finca_name}.xlsx"
            wb = openpyxl.Workbook()
            wb.active.append(["ID", "Factor", "Mueve semanas", "Vigencia", "Bloqueado"])
            wb.save(path)
            ajustes_files[finca_code] = {"output": str(path), "ajustes_rows": 1, "missing_rows": 0}
        return ajustes_files

    def test_notify_tika_ajuste_sends_email_with_filled_workbook_and_ajustes_files(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            template_path = Path(tmp_dir) / "template.xlsx"
            self._write_template(template_path)
            ajustes_files = self._write_ajustes_files(tmp_dir)

            with patch(
                "app.services.etl_jobs.planos_proyeccion_generator.settings.PLANOS_PROYECCION_TIKA_TEMPLATE_PATH",
                str(template_path),
            ), patch(
                "app.services.etl_jobs.planos_proyeccion_generator.settings.PLANOS_PROYECCION_TIKA_EMAILS",
                ["estadistica@inverpalmas.com"],
            ), patch(
                "app.services.etl_jobs.planos_proyeccion_generator.settings.PLANOS_PROYECCION_TIKA_CC_EMAILS",
                [],
            ), patch(
                "app.services.etl_jobs.planos_proyeccion_generator.send_email"
            ) as mock_send:
                resultado = _notify_tika_ajuste(self._build_matched(), ajustes_files, Path(tmp_dir))

            mock_send.assert_called_once()
            _, kwargs = mock_send.call_args
            self.assertEqual(kwargs["to"], ["estadistica@inverpalmas.com"])
            self.assertIsNone(kwargs["cc"])
            self.assertEqual(len(kwargs["attachments"]), 3)
            for attachment in kwargs["attachments"]:
                self.assertTrue(attachment.exists())
            self.assertEqual(resultado["hoja2_rows"], 3)
            self.assertEqual(len(resultado["ajustes_files"]), 2)

    def test_notify_tika_ajuste_skips_send_when_ajustes_file_missing(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            template_path = Path(tmp_dir) / "template.xlsx"
            self._write_template(template_path)
            ajustes_files = {
                "002": {"output": str(Path(tmp_dir) / "no_existe.xlsx")},
            }

            with patch(
                "app.services.etl_jobs.planos_proyeccion_generator.settings.PLANOS_PROYECCION_TIKA_TEMPLATE_PATH",
                str(template_path),
            ), patch(
                "app.services.etl_jobs.planos_proyeccion_generator.send_email"
            ) as mock_send:
                resultado = _notify_tika_ajuste(self._build_matched(), ajustes_files, Path(tmp_dir))

            mock_send.assert_not_called()
            self.assertIsNone(resultado)


if __name__ == "__main__":
    unittest.main()
