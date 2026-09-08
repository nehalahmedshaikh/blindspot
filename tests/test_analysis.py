import unittest

from blindspot.analysis import (
    bootstrap_mean_interval,
    leave_one_series_out,
    missingness_concentration,
    variance_decomposition,
)


class AnalysisTests(unittest.TestCase):
    def test_bootstrap_interval_is_deterministic_and_contains_mean(self):
        first = bootstrap_mean_interval([0.1, 0.2, 0.3, 0.4], 200, "test")
        second = bootstrap_mean_interval([0.1, 0.2, 0.3, 0.4], 200, "test")
        self.assertEqual(first, second)
        self.assertLessEqual(first[0], 0.25)
        self.assertGreaterEqual(first[1], 0.25)

    def test_variance_decomposition_separates_country_and_indicator(self):
        rows = [
            {"country_alpha3": country, "series_code": series, "missingness": value}
            for country, values in {"AAA": [0.0, 1.0], "BBB": [0.0, 1.0]}.items()
            for series, value in zip(("S1", "S2"), values)
        ]
        result = variance_decomposition(rows)
        self.assertEqual(result["country_percent"], 0.0)
        self.assertEqual(result["indicator_percent"], 100.0)
        self.assertEqual(result["interaction_and_residual_percent"], 0.0)


    def test_leave_one_series_out_reports_every_estimate(self):
        rows = []
        for country, income, values in (
            ("HIG", "High income", (0.1, 0.2)),
            ("LOW", "Low income", (0.5, 0.7)),
        ):
            for series, value in zip(("S1", "S2"), values):
                rows.append(
                    {
                        "country_alpha3": country,
                        "country_name": country,
                        "income_group": income,
                        "region": "Region",
                        "population": 1,
                        "series_code": series,
                        "missingness": value,
                        "staleness": value,
                    }
                )
        result = leave_one_series_out(rows, {})
        self.assertEqual(len(result["estimates"]), 2)
        self.assertEqual(result["baseline_low_minus_high_income_pp"], 45.0)
        self.assertEqual(result["minimum_pp"], 40.0)
        self.assertEqual(result["maximum_pp"], 50.0)

    def test_missingness_concentration_ranks_series(self):
        rows = [
            {"series_code": "S1", "goal": 1, "missingness": 1.0},
            {"series_code": "S1", "goal": 1, "missingness": 1.0},
            {"series_code": "S2", "goal": 2, "missingness": 0.1},
            {"series_code": "S2", "goal": 2, "missingness": 0.1},
        ]
        result = missingness_concentration(rows, {})
        self.assertEqual(result["top_series"][0]["series_code"], "S1")
        self.assertEqual(result["top_quintile_series"], 1)
        self.assertEqual(result["top_quintile_share_of_missingness_pct"], 90.9)


if __name__ == "__main__":
    unittest.main()
