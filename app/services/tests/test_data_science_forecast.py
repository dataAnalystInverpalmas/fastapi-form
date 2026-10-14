import unittest

import numpy as np
import pandas as pd

from app.services.data_science.production_forecast import SEASON, _backtest, _fit_predict, _seasonal_index


def _synthetic_series(years: int = 4, noise: float = 0.0) -> pd.Series:
    index = pd.date_range("2021-01-04", periods=SEASON * years, freq="W-MON")
    weeks = np.minimum(index.isocalendar().week.to_numpy().astype(int), SEASON)
    pattern = np.where(weeks == 6, 2.0, 1.0)  # pico tipo San Valentin
    rng = np.random.default_rng(0)
    values = 1000 * pattern * (1 + noise * rng.standard_normal(len(index)))
    return pd.Series(values, index=index)


class ProductionForecastTests(unittest.TestCase):
    def test_seasonal_index_detects_peak_week(self):
        index = _seasonal_index(_synthetic_series())
        self.assertEqual(int(index.idxmax()), 6)
        self.assertAlmostEqual(float(index.mean()), 1.0, places=6)

    def test_forecast_reproduces_clean_pattern(self):
        series = _synthetic_series()
        forecast = _fit_predict(series, 12)
        self.assertEqual(len(forecast), 12)
        self.assertEqual(forecast.index[0], series.index[-1] + pd.Timedelta(weeks=1))
        peak_weeks = forecast[forecast.index.isocalendar().week == 6]
        normal_weeks = forecast[forecast.index.isocalendar().week != 6]
        self.assertGreater(peak_weeks.min(), normal_weeks.max())

    def test_backtest_reports_errors_and_baseline(self):
        result = _backtest(_synthetic_series(noise=0.05), 8)
        self.assertGreater(result["origenes"], 0)
        self.assertLess(result["wape_modelo"], 0.2)
        self.assertIsNotNone(result["wape_ingenuo"])
        self.assertLess(result["q10"], result["q90"])


if __name__ == "__main__":
    unittest.main()
