import unittest

import pandas as pd

from app.services.etl_jobs.balance_masas_generator import (
    build_base_fincas,
    build_datos_exportado,
    build_real_vs_presupuesto,
    distribuir_por_finca,
    prepare_exportado,
    prepare_lonas,
    prepare_matas,
)


def _exportado() -> pd.DataFrame:
    base = {
        "ano": "2025", "mes": 1, "flor": "CLA", "zusa": 0, "zeuro": 0, "zotros": 0, "bajas_a": 0,
        "ingnaciona": 0, "bajas_nac": 0, "compras": 0, "obsequios": 0, "desechos": 0, "inicial": 0,
    }
    return pd.DataFrame([
        {**base, "grado": "FAN", "produccion": 300.0, "expble": 300.0, "exptdo": 250.0, "nacional": 0.0},
        {**base, "grado": "NAL", "produccion": 100.0, "expble": 0.0, "exptdo": 0.0, "nacional": 100.0},
        {**base, "grado": "", "produccion": 50.0, "expble": 0.0, "exptdo": 0.0, "nacional": 0.0},
    ])


class BalanceMasasTests(unittest.TestCase):
    def test_exportado_drops_empty_grado_and_computes_share(self) -> None:
        df = prepare_exportado(_exportado())
        self.assertEqual(sorted(df["grado"]), ["FAN", "NAL"])
        self.assertAlmostEqual(df.loc[df["grado"] == "FAN", "%grado"].iloc[0], 0.75)

    def test_distribution_by_finca_preserves_totals(self) -> None:
        df = prepare_exportado(_exportado())
        lonas = pd.DataFrame({
            "fecha": ["2025-01-10", "2025-01-11"],
            "flor": ["CLA", "CLA"],
            "finca": ["001", "002"],
            "lonas": [60, 40],
        })
        dframe0 = distribuir_por_finca(df, prepare_lonas(lonas))
        self.assertAlmostEqual(dframe0["produccion"].sum(), 400.0)
        por_finca = dframe0.groupby("finca")["produccion"].sum()
        self.assertAlmostEqual(por_finca["001"], 240.0)
        self.assertAlmostEqual(por_finca["002"], 160.0)

        keys = ["finca", "flor", "ano", "mes"]
        areas = pd.DataFrame({"finca": ["001", "002"], "flor": ["CLA"] * 2, "ano": [2025] * 2, "mes": [1] * 2, "metros": [100.0, 80.0]})
        pto = pd.DataFrame({"finca": ["001", "002"], "flor": ["CLA"] * 2, "ano": [2025] * 2, "mes": [1] * 2, "presupuesto": [200.0, 150.0]})
        matas = pd.DataFrame({"finca": ["001", "002"], "flor": ["CLA"] * 2, "ano": [2025] * 2, "mes": [1] * 2, "matas": [1000.0, 0.0]})
        base = build_base_fincas(dframe0, areas, pto, matas).set_index("finca")

        # metros/presupuesto/matas no se duplican por grado y el total 000 los suma.
        self.assertAlmostEqual(base.loc["001", "metros"], 100.0)
        self.assertAlmostEqual(base.loc["002", "presupuesto"], 150.0)
        self.assertAlmostEqual(base.loc["000", "presupuesto"], 350.0)
        self.assertAlmostEqual(base.loc["001", "FM2_produccion"], 2.4)
        self.assertAlmostEqual(base.loc["000", "%nacional"], 0.25)
        # division por cero en matas no deja infinitos
        self.assertTrue(pd.isna(base.loc["002", "FMata_produccion"]))

        datos = build_datos_exportado(base.reset_index())
        self.assertEqual(set(datos.columns), {*keys, "variable", "valor"})
        self.assertEqual(len(datos), 3 * 10)

    def test_matas_take_last_cut_of_month(self) -> None:
        plantas = pd.DataFrame({
            "fecha": ["2025-01-05", "2025-01-05", "2025-01-20", "bad"],
            "flor": ["CLA"] * 4,
            "finca": ["001"] * 4,
            "matas": [10, 5, 30, 99],
        })
        result = prepare_matas(plantas)
        self.assertEqual(result["matas"].tolist(), [30])

    def test_real_vs_presupuesto_applies_exportable_factor(self) -> None:
        df = prepare_exportado(_exportado())
        pto = pd.DataFrame({"ano": [2025, 2025], "mes": [1, 1], "flor": ["CLA", "ROS"], "finca": ["001", "001"], "presupuesto": [1000.0, 1000.0]})
        tidy = build_real_vs_presupuesto(df, pto, 2023, {"CLA": 0.92}, 0.90)
        pto_exp = tidy[(tidy["origen"] == "pto") & (tidy["variable"] == "exportable")].set_index("flor")["tallos"]
        self.assertEqual(pto_exp["CLA"], 920.0)
        self.assertEqual(pto_exp["ROS"], 900.0)
        self.assertEqual(set(tidy["periodo"]), {"202501"})


if __name__ == "__main__":
    unittest.main()
