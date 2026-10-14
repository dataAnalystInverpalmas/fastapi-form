import unittest

import pandas as pd

from app.services.etl_jobs.anomalias_lonas_generator import (
    _analyze_group,
    _build_correcciones_plantas,
    _build_correcciones_tallos,
    _rango_semanas,
)


def _group(tallos: list, plantas: list) -> pd.DataFrame:
    n = len(tallos)
    return pd.DataFrame(
        {
            "fecha_registro": pd.date_range("2026-01-05", periods=n, freq="D"),
            "tallos": tallos,
            "plantas": plantas,
            "flor": ["CLA"] * n,
            "finca": ["001"] * n,
            "bloque": [1] * n,
            "variedad": ["MOON"] * n,
            "cosecha": ["2026"] * n,
        }
    )


def _analizar(group_df: pd.DataFrame, plantas_referencia: float | None = None) -> pd.DataFrame:
    result = _analyze_group(group_df=group_df, siembra_yyww=2552, plantas_ref=100, festivos=set())
    result["siembra_yyww"] = pd.array(result["siembra_yyww"], dtype="Int64")
    result["plantas_referencia"] = plantas_referencia
    return result


def _row(result: pd.DataFrame, fecha: str) -> pd.Series:
    return result.loc[result["fecha_registro"] == pd.Timestamp(fecha)].iloc[0]


class AnomaliasLonasTests(unittest.TestCase):
    def test_rango_semanas_incluye_semanas_completas(self) -> None:
        # 2640 va del lunes 28/09/2026 al domingo 04/10/2026
        inicio, fin = _rango_semanas(2640, 2641)

        self.assertEqual(inicio, pd.Timestamp("2026-09-28"))
        self.assertEqual(fin, pd.Timestamp("2026-10-11"))

    def test_zero_tallos_is_not_flagged_as_missing_data(self) -> None:
        result = _analizar(_group([20, 20, 20, 20, 20, 20, 20, 0], [100] * 8))

        row = _row(result, "2026-01-12")
        self.assertFalse(row["es_anomalo"])
        self.assertEqual(row["motivo"], "normal")

    def test_plantas_cero_es_plantas_invalidas_y_no_regla_fisica(self) -> None:
        result = _analizar(_group([20, 20, 20, 20, 20], [100, 110, 120, 0, 100]))

        row = _row(result, "2026-01-08")
        self.assertTrue(row["es_anomalo"])
        self.assertEqual(row["motivo"], "plantas_invalidas")
        # media de los 3 días de corte previos: (100 + 110 + 120) / 3
        self.assertEqual(row["plantas_media_3d"], 110)

    def test_tallos_y_plantas_en_cero_no_es_anomalia(self) -> None:
        result = _analizar(_group([20, 20, 0], [100, 100, 0]))

        row = _row(result, "2026-01-07")
        self.assertFalse(row["es_anomalo"])
        self.assertEqual(row["motivo"], "normal")

    def test_plantas_nulas_al_inicio_usan_los_dias_siguientes(self) -> None:
        result = _analizar(_group([20, 20, 20, 20, 20], [None, 90, 100, 110, 500]))

        row = _row(result, "2026-01-05")
        self.assertEqual(row["motivo"], "plantas_invalidas")
        self.assertEqual(row["plantas_media_3d"], 100)

    def test_correccion_plantas_prefiere_referencia_de_la_siembra(self) -> None:
        result = _analizar(_group([20, 20, 20, 20], [100, 100, 100, 0]), plantas_referencia=150)

        correcciones = _build_correcciones_plantas(result)

        self.assertEqual(len(correcciones), 1)
        fila = correcciones.iloc[0]
        self.assertEqual(fila["semana_siembra"], 2552)
        self.assertEqual(fila["semana_registro"], 2602)
        self.assertEqual(fila["plantas_actual"], 0)
        self.assertEqual(fila["plantas_sugeridas"], 150)
        self.assertEqual(fila["fuente_sugerencia"], "finca_bloque_variedad_siembra")

    def test_correccion_plantas_sin_referencia_usa_media_3_dias(self) -> None:
        result = _analizar(_group([20, 20, 20, 20], [100, 100, 100, 0]))

        fila = _build_correcciones_plantas(result).iloc[0]

        self.assertEqual(fila["plantas_sugeridas"], 100)
        self.assertEqual(fila["fuente_sugerencia"], "media_3_dias_corte")

    def test_tallos_mayor_mitad_por_plantas_mal_digitadas(self) -> None:
        # 60 tallos con 100 plantas viola la regla; con las 1000 de la siembra no
        result = _analizar(_group([300, 310, 290, 60], [1000, 1000, 1000, 100]), plantas_referencia=1000)

        correcciones = _build_correcciones_tallos(result)

        self.assertEqual(len(correcciones), 1)
        fila = correcciones.iloc[0]
        self.assertEqual(fila["accion_sugerida"], "corregir_plantas")
        self.assertEqual(fila["valor_sugerido"], 1000)

    def test_tallos_mayor_mitad_por_tallos_mal_digitados(self) -> None:
        result = _analizar(_group([20, 30, 40, 900], [100, 100, 100, 100]), plantas_referencia=100)

        fila = _build_correcciones_tallos(result).iloc[0]

        self.assertEqual(fila["tallos"], 900)
        self.assertEqual(fila["accion_sugerida"], "corregir_tallos")
        self.assertEqual(fila["valor_sugerido"], 30)


if __name__ == "__main__":
    unittest.main()
