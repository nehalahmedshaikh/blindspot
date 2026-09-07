import unittest

from blindspot.config import Country, SeriesSpec
from blindspot.metrics import calculate_metrics, is_aggregate, percentile_ranks


class MetricTests(unittest.TestCase):
    def setUp(self):
        self.countries = [
            Country("AA", "AAA", "1", "Aland"),
            Country("BB", "BBB", "2", "Bland"),
        ]
        self.specs = [
            SeriesSpec(1, "TEST", 1, "universal", "test series"),
            SeriesSpec(14, "SEA", 2, "conditional", "conditional series"),
        ]
        self.context = {
            "AAA": {"population": 100, "population_year": 2024, "region": "R1", "income_group": "Low"},
            "BBB": {"population": 1000, "population_year": 2024, "region": "R2", "income_group": "High"},
        }
        self.catalog = {
            "TEST": {"description": "Test indicator", "indicator": ["1.1.1"]},
            "SEA": {"description": "Sea indicator", "indicator": ["14.1.1"]},
        }

    @staticmethod
    def observation(country, series, year, nature="C", dimensions=None):
        return {
            "country_m49": country,
            "country_name": country,
            "series_code": series,
            "reference_year": year,
            "nature": nature,
            "dimensions": dimensions or {"Sex": "BOTHSEX", "Age": "ALLAGE"},
        }

    def test_priority_is_bounded_and_conditional_is_excluded(self):
        observations = [self.observation("1", "TEST", year) for year in range(2021, 2026)]
        result = calculate_metrics(
            observations, self.specs, self.countries, self.context, self.catalog, completed_year=2025
        )
        pairs = {(item["country_alpha3"], item["series_code"]): item for item in result["country_series"]}
        self.assertEqual(pairs[("AAA", "TEST")]["recent_completeness"], 1)
        self.assertEqual(pairs[("BBB", "TEST")]["recent_completeness"], 0)
        self.assertIsNone(pairs[("AAA", "SEA")]["measurement_priority_v1"])
        self.assertTrue(0 <= pairs[("BBB", "TEST")]["measurement_priority_v1"] <= 100)

    def test_disaggregation_and_aggregate_are_distinct(self):
        rows = [
            self.observation("1", "TEST", 2024, dimensions={"Sex": "FEMALE"}),
            self.observation("1", "TEST", 2024, dimensions={"Sex": "MALE"}),
        ]
        result = calculate_metrics(
            rows, self.specs, self.countries, self.context, self.catalog, completed_year=2025
        )
        pair = next(x for x in result["country_series"] if x["country_alpha3"] == "AAA" and x["series_code"] == "TEST")
        self.assertTrue(pair["disaggregation"]["sex"])
        self.assertFalse(pair["has_aggregate_slice"])

    def test_tied_percentiles_and_aggregate_detection(self):
        ranks = percentile_ranks({"a": 1, "b": 2, "c": 2, "missing": None})
        self.assertEqual(ranks["missing"], 0.5)
        self.assertEqual(ranks["b"], ranks["c"])
        self.assertTrue(is_aggregate({"Sex": "BOTHSEX", "Age": "ALLAGE"}))
        self.assertFalse(is_aggregate({"Sex": "FEMALE"}))


if __name__ == "__main__":
    unittest.main()
