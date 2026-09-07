import unittest

from blindspot.sources import _normalize_observation, query_url


class SourceTests(unittest.TestCase):
    def test_query_url_encodes_repeated_parameters(self):
        url = query_url(
            "https://example.test", {"seriesCode": ["A", "B"], "timePeriod": [2015, 2016], "page": 1}
        )
        self.assertIn("seriesCode=A", url)
        self.assertIn("seriesCode=B", url)
        self.assertIn("page=1", url)
        self.assertIn("timePeriod=2015", url)
        self.assertIn("timePeriod=2016", url)

    def test_normalization_preserves_status_and_dimensions(self):
        row = _normalize_observation(
            {
                "geoAreaCode": "008",
                "geoAreaName": "Albania",
                "series": "X",
                "timePeriodStart": 2022.0,
                "value": "4.2",
                "attributes": {"Nature": "E", "Units": "PERCENT"},
                "dimensions": {"Sex": "BOTHSEX", "Reporting Type": "G"},
                "source": "Official",
            },
            "2026-09-07",
        )
        self.assertEqual(row["country_m49"], "8")
        self.assertEqual(row["reference_year"], 2022)
        self.assertEqual(row["nature"], "E")
        self.assertEqual(row["reporting_type"], "G")


if __name__ == "__main__":
    unittest.main()
