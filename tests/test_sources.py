import unittest

from blindspot.config import SeriesSpec
from blindspot.sources import (
    SourceError,
    _normalize_observation,
    _validate_representative_mapping,
    query_url,
)


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

    def test_representative_mapping_must_match_official_catalogue(self):
        catalog = {
            "A": {"indicator": ["1.1.1"]},
            "B": {"indicator": ["1.2.1"]},
        }
        valid = [
            SeriesSpec(1, "A", 1, "universal", "A", indicators=["1.1.1"]),
            SeriesSpec(1, "B", 1, "universal", "B", indicators=["1.2.1"]),
        ]
        _validate_representative_mapping(valid, catalog)
        with self.assertRaises(SourceError):
            _validate_representative_mapping(valid[:1], catalog)
        duplicated = valid + [
            SeriesSpec(1, "B", 1, "universal", "B again", indicators=["1.1.1"])
        ]
        with self.assertRaises(SourceError):
            _validate_representative_mapping(duplicated, catalog)

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
