import unittest

import pandas as pd

from app.services.etl_jobs.explicar_brecha_tika_generator import (
    KEY,
    agregar_total,
    cascada_larga,
    construir_cascada,
    demanda_modelo,
    descomponer_paso,
    tika_cohortes,
)

VARI = pd.DataFrame({"variedad": ["DONCEL", "HERMES"], "color": ["ROSADO", "AMARILLO"], "flor": ["CLA", "CLA"]})
SEMANAS = pd.DataFrame(
    {"aass": [2601, 2619, 2620, 2621, 2622], "fecha": pd.to_datetime(["2025-12-29", "2026-05-04", "2026-05-11", "2026-05-18", "2026-05-25"])}
)


def _coh(rows: list[tuple], conocidas: bool = True) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=KEY + ["plantas", "tallos"])
    df["plantas_conocidas"] = conocidas
    return df


def _dem(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["flor", "color", "variedad", "tallos"])


class DescomponerPasoTests(unittest.TestCase):
    def test_mas_plantas_misma_productividad_es_siembra(self) -> None:
        prev = _coh([("CLA", "ROSADO", "DONCEL", "2025-12", 1000, 500)])
        curr = _coh([("CLA", "ROSADO", "DONCEL", "2025-12", 1500, 750)])
        paso = descomponer_paso(prev, curr).iloc[0]
        self.assertAlmostEqual(paso["siembras"], 250)
        self.assertAlmostEqual(paso["productividad"], 0)

    def test_mismas_plantas_mas_tallos_es_productividad(self) -> None:
        prev = _coh([("CLA", "ROSADO", "DONCEL", "2025-12", 1000, 500)])
        curr = _coh([("CLA", "ROSADO", "DONCEL", "2025-12", 1000, 800)])
        paso = descomponer_paso(prev, curr).iloc[0]
        self.assertAlmostEqual(paso["siembras"], 0)
        self.assertAlmostEqual(paso["productividad"], 300)

    def test_cohorte_nueva_y_eliminada(self) -> None:
        prev = _coh([("CLA", "ROSADO", "DONCEL", "2025-12", 1000, 500)])
        curr = _coh([("CLA", "AMARILLO", "HERMES", "2026-01", 2000, 900)])
        paso = descomponer_paso(prev, curr).set_index("variedad")
        self.assertAlmostEqual(paso.loc["DONCEL", "siembras"], -500)
        self.assertAlmostEqual(paso.loc["HERMES", "siembras"], 900)
        self.assertAlmostEqual(paso["productividad"].abs().sum(), 0)

    def test_sin_dato_de_plantas_va_a_productividad(self) -> None:
        prev = _coh([("CLA", "ROSADO", "DONCEL", "2025-12", 1000, 500)])
        curr = _coh([("CLA", "ROSADO", "DONCEL", "2025-12", 0, 700)], conocidas=False)
        paso = descomponer_paso(prev, curr).iloc[0]
        self.assertAlmostEqual(paso["siembras"], 0)
        self.assertAlmostEqual(paso["productividad"], 200)


class ConstruirCascadaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.etapas = ["A", "B", "Real"]
        self.cohortes = {
            "A": _coh([("CLA", "ROSADO", "DONCEL", "2025-12", 1000, 500), ("CLA", "AMARILLO", "HERMES", "2026-01", 400, 100)]),
            "B": _coh([("CLA", "ROSADO", "DONCEL", "2025-12", 1200, 600)]),
            "Real": _coh([("CLA", "ROSADO", "DONCEL", "2025-12", 1200, 900), ("CLA", "AMARILLO", "HERMES", "2026-01", 400, 50)]),
        }
        self.demandas = {
            "A": _dem([("CLA", "ROSADO", "DONCEL", 550), ("CLA", "AMARILLO", "HERMES", 100)]),
            "B": _dem([("CLA", "ROSADO", "DONCEL", 500), ("CLA", "AMARILLO", "HERMES", 100)]),
            "Real": _dem([("CLA", "ROSADO", "DONCEL", 450), ("CLA", "AMARILLO", "HERMES", 100)]),
        }

    def test_cascada_cuadra_y_extremos_correctos(self) -> None:
        tabla = construir_cascada(self.etapas, self.cohortes, self.demandas, ["flor", "color"])
        self.assertLess(tabla["Cuadre"].abs().max(), 1e-9)
        rosado = tabla.set_index("color").loc["ROSADO"]
        self.assertAlmostEqual(rosado["Brecha A"], -50)
        self.assertAlmostEqual(rosado["A->B: siembras"], 100)
        self.assertAlmostEqual(rosado["A->B: demanda"], 50)
        self.assertAlmostEqual(rosado["B->Real: productividad y ejecucion"], 300)
        self.assertAlmostEqual(rosado["B->Real: demanda"], 50)
        self.assertAlmostEqual(rosado["Brecha Real"], 450)

    def test_total_y_formato_largo(self) -> None:
        tabla = construir_cascada(self.etapas, self.cohortes, self.demandas, ["flor"])
        total = agregar_total(tabla, ["flor"]).iloc[-1]
        self.assertEqual(total["flor"], "TOTAL")
        self.assertAlmostEqual(total["Brecha Real"], (900 + 50) - (450 + 100))
        largo = cascada_larga(tabla, ["flor"])
        self.assertEqual(largo.iloc[0]["escalon"], "Brecha A")
        self.assertEqual(largo.iloc[-1]["escalon"], "Brecha Real")
        cambios = largo[largo["tipo"] == "cambio"]["tallos"].sum()
        self.assertAlmostEqual(largo.iloc[0]["tallos"] + cambios, largo.iloc[-1]["tallos"])


class LecturaTikaTests(unittest.TestCase):
    def test_plantas_por_cama_sin_duplicar_y_tallos_solo_en_ventana(self) -> None:
        base = {
            "variedad": "DONCEL", "color": "ROSADO", "flor": "CLAVEL", "cosecha": "JU2626",
            "semanasiembra": 2601, "cantidadsembradafutura": 900, "cantidadsembrada": None,
            "finca": "PALMAS", "bloque": 16, "nave": 1, "tabla": "A",
        }
        raw = pd.DataFrame(
            [
                {**base, "cama": 1, "semanaproducion": 2619, "cantidad": 10},
                {**base, "cama": 1, "semanaproducion": 2620, "cantidad": 20},
                {**base, "cama": 1, "semanaproducion": 2621, "cantidad": 30},
                {**base, "cama": 2, "semanaproducion": 2621, "cantidad": 5},
                # otra cosecha sembrada el mismo mes: es la misma cohorte
                {**base, "cama": 3, "cosecha": "JL2630", "semanaproducion": 2620, "cantidad": 7},
            ]
        )
        coh, semanal = tika_cohortes(raw, VARI, SEMANAS, pd.Timestamp("2026-05-11"), pd.Timestamp("2026-05-18"))
        self.assertEqual(len(coh), 1)
        fila = coh.iloc[0]
        self.assertEqual(fila["flor"], "CLA")
        self.assertEqual(fila["mes_siembra"], "2025-12")
        self.assertEqual(fila["plantas"], 2700)
        self.assertEqual(fila["tallos"], 62)
        self.assertEqual(semanal["tallos"].sum(), 62)

    def test_demanda_modelo_lee_miles_con_coma(self) -> None:
        raw = pd.DataFrame({"item_demanda": ["DONCEL", "OTRA"], "semana": [2620, 2620], "cantidad": ["6,000", "1,500"],
                            "flor": ["CLAVEL", "CLAVEL"], "fecha": ["2026-05-11", "2026-05-11"]})
        dem = demanda_modelo(raw, VARI, SEMANAS).set_index("variedad")
        self.assertEqual(dem.loc["DONCEL", "tallos"], 6000)
        self.assertEqual(dem.loc["DONCEL", "color"], "ROSADO")
        self.assertEqual(dem.loc["OTRA", "flor"], "CLA")
        self.assertEqual(dem.loc["OTRA", "color"], "SIN_MAPEO")


if __name__ == "__main__":
    unittest.main()
