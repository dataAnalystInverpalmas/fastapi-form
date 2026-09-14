from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app.services.etl_jobs import compare_tika_produccion_generator as compare_mod
from app.services.etl_jobs import comparar_picos_demanda_generator as picos_demanda_mod
from app.services.etl_jobs import proyecciones_generator as proy_mod


class ProyeccionesGeneratorIntegrityTest(unittest.TestCase):
    def test_generate_proyecciones_csv_aggregates_matas_and_tallos_on_output_key(self):
        df_proy = pd.DataFrame(
            [
                {
                    "finca": "001",
                    "flor": "CLA",
                    "bloque": 28,
                    "variedad": "WALKER",
                    "cosecha": "FE2705",
                    "fecha": "2023-09-20",
                    "matas": 11292,
                    "edad": 36,
                    "tipo": "PT",
                    "tallos": 0,
                },
                {
                    "finca": "001",
                    "flor": "CLA",
                    "bloque": 28,
                    "variedad": "WALKER",
                    "cosecha": "FE2705",
                    "fecha": "2023-09-20",
                    "matas": 13100,
                    "edad": 36,
                    "tipo": "PT",
                    "tallos": 0,
                },
                {
                    "finca": "001",
                    "flor": "CLA",
                    "bloque": 28,
                    "variedad": "WALKER",
                    "cosecha": "FE2705",
                    "fecha": "2023-09-20",
                    "matas": 1768,
                    "edad": 36,
                    "tipo": "PT",
                    "tallos": 0,
                },
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "proyecciones.csv"
            with (
                patch.object(proy_mod, "_load_proyecciones_dbf", return_value=df_proy),
                patch.object(
                    proy_mod,
                    "_load_db_data",
                    return_value=(
                        pd.DataFrame(),
                        pd.DataFrame([{"variedad": "WALKER", "ncolor": "ROJO"}]),
                        pd.DataFrame([{"cosecha": "FE2705", "ncosecha": "FE2705"}]),
                    ),
                ),
                patch.object(proy_mod.settings, "PROYECCIONES_OUTPUT_PATH", str(output_path), create=True),
                patch.object(proy_mod, "dataframe_to_sql"),
            ):
                _, audit = proy_mod.generate_proyecciones_csv(debug=True)

            self.assertEqual(audit["pre_export_rows"], 1)
            final = pd.read_csv(output_path)
            self.assertEqual(final.loc[0, "matas"], 26160)
            self.assertEqual(final.loc[0, "tallos"], 0)

    def test_normalize_finca_code_standardizes_all_source_formats(self):
        entries = ["INVERPALMAS", "PALERMO", "001", "002", "1", "2", "001.0", "002.0", None]
        expected = ["001", "002", "001", "002", "001", "002", "001", "002", "000"]
        self.assertEqual([picos_demanda_mod._normalize_finca_code(value) for value in entries], expected)

    def test_generate_proyecciones_csv_tracks_counts_through_transforms(self):
        df_proy = pd.DataFrame(
            [
                {
                    "finca": "001",
                    "flor": "CLA",
                    "bloque": 1,
                    "variedad": "VAR1",
                    "cosecha": "OH25S",
                    "fecha": "2025-01-06",
                    "matas": 10,
                    "edad": 10,
                    "tipo": "Proy",
                    "tallos": 100,
                },
                {
                    "finca": "001",
                    "flor": "CLA",
                    "bloque": 1,
                    "variedad": "VAR1",
                    "cosecha": "OH25S",
                    "fecha": "2025-01-13",
                    "matas": 10,
                    "edad": 11,
                    "tipo": "Proy",
                    "tallos": 150,
                },
            ]
        )
        df_pto = pd.DataFrame(
            [
                {
                    "finca": "001",
                    "flor": "CLA",
                    "bloque": 2,
                    "variedad": "VAR2",
                    "cosecha": "OH25S",
                    "fecha": "2025-01-20",
                    "edad": 12,
                    "ncolor": "Rojo",
                    "tallos": 80,
                    "matas": 8,
                }
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "proyecciones.csv"

            with (
                patch.object(proy_mod, "_load_proyecciones_dbf", return_value=df_proy),
                patch.object(
                    proy_mod,
                    "_load_db_data",
                    return_value=(
                        df_pto,
                        pd.DataFrame([
                            {"variedad": "VAR1", "ncolor": "Blanco"},
                            {"variedad": "VAR2", "ncolor": "Rojo"},
                        ]),
                        pd.DataFrame([{"cosecha": "OH25S", "ncosecha": "OH25S"}]),
                    ),
                ),
                patch.object(proy_mod.settings, "PROYECCIONES_OUTPUT_PATH", str(output_path), create=True),
                patch.object(proy_mod, "dataframe_to_sql"),
            ):
                output, audit = proy_mod.generate_proyecciones_csv(debug=True)

            self.assertEqual(str(output_path), output)
            self.assertTrue(output_path.exists())
            self.assertEqual(audit["dbf_loaded_rows"], 2)
            self.assertEqual(audit["db_rows"], 1)
            self.assertEqual(audit["combined_rows"], 3)
            self.assertEqual(audit["date_valid_rows"], 3)
            self.assertEqual(audit["raw_tipo_max_fecha"], {"Proy": "2025-01-13"})
            self.assertEqual(audit["final_tipo_max_fecha"], {"PT": "2025-01-20", "Proy": "2025-01-13"})
            self.assertEqual(
                audit["common_tipo_max_fecha_compare"],
                {"raw": {"Proy": "2025-01-13"}, "final": {"Proy": "2025-01-13"}, "match": True},
            )
            self.assertGreaterEqual(audit["final_rows"], 2)

    def test_generate_proyecciones_csv_preserves_aj_in_re_tipo_counts(self):
        """AJ/IN/RE rows with unique groupby keys must survive 1-to-1 through the pipeline."""
        rows = []
        for bloque, tipo in enumerate(["AJ", "IN", "RE"], start=10):
            for mes in ["11", "12"]:
                rows.append({
                    "finca": "001",
                    "flor": "CLA",
                    "bloque": bloque,
                    "variedad": "VAR1",
                    "cosecha": "OH25S",
                    "fecha": f"2026-{mes}-02",
                    "matas": 10,
                    "edad": bloque,
                    "tipo": tipo,
                    "tallos": 100,
                })
        df_proy = pd.DataFrame(rows)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "proyecciones.csv"
            with (
                patch.object(proy_mod, "_load_proyecciones_dbf", return_value=df_proy),
                patch.object(
                    proy_mod,
                    "_load_db_data",
                    return_value=(
                        pd.DataFrame(),
                        pd.DataFrame([{"variedad": "VAR1", "ncolor": "Blanco"}]),
                        pd.DataFrame([{"cosecha": "OH25S", "ncosecha": "OH25S"}]),
                    ),
                ),
                patch.object(proy_mod.settings, "PROYECCIONES_OUTPUT_PATH", str(output_path), create=True),
                patch.object(proy_mod, "dataframe_to_sql"),
            ):
                _, audit = proy_mod.generate_proyecciones_csv(debug=True)

        for tipo in ["AJ", "IN", "RE"]:
            self.assertEqual(
                audit["tipo_counts_dbf"].get(tipo, 0),
                audit["tipo_counts_final"].get(tipo, 0),
                msg=f"tipo={tipo}: conteo cambió entre entrada y salida",
            )

    def test_load_proyecciones_compare_keeps_future_aj_rows(self):
        df_vari = pd.DataFrame([
            {"variedad": "VAR1", "color": "Rojo", "flor": "CLA"},
            {"variedad": "VAR2", "color": "Azul", "flor": "CLA"},
        ])

        csv_rows = pd.DataFrame([
            {"fecha": "2026-11-02", "flor": "CLA", "tipo": "AJ",     "tallos": 100, "variedad": "VAR1", "ncolor": "Rojo"},
            {"fecha": "2026-11-09", "flor": "CLA", "tipo": "PROYAJ", "tallos": 150, "variedad": "VAR2", "ncolor": "Azul"},
        ])

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "proyecciones.csv"
            csv_rows.to_csv(output_path, index=False)

            with patch.object(compare_mod.settings, "PROYECCIONES_OUTPUT_PATH", str(output_path), create=True):
                datos_re, datos_in, datos_aj, datos_pt = compare_mod._load_proyecciones_compare(df_vari)

        self.assertFalse(datos_aj.empty)
        self.assertEqual(set(datos_aj["tipo"].unique()), {"Proy_Aj"})
        self.assertAlmostEqual(datos_aj["tallos"].sum(), 225.0)
        self.assertEqual(len(datos_pt), 0)
        self.assertEqual(len(datos_re), 0)
        self.assertEqual(len(datos_in), 0)



if __name__ == "__main__":
    unittest.main()
