import json
import unittest
from pathlib import Path

from blindspot.config import PROJECT_ROOT, load_countries, load_series


class ConfigurationTests(unittest.TestCase):
    def test_exactly_three_unique_series_per_goal(self):
        specs = load_series()
        self.assertEqual(len(specs), 51)
        self.assertEqual(len({item.code for item in specs}), 51)
        self.assertEqual(
            {goal: sum(item.goal == goal for item in specs) for goal in range(1, 18)},
            {goal: 3 for goal in range(1, 18)},
        )

    def test_country_registry_has_193_unique_members(self):
        countries = load_countries()
        self.assertEqual(len(countries), 193)
        self.assertEqual(len({item.m49 for item in countries}), 193)
        self.assertEqual(len({item.alpha3 for item in countries}), 193)

    def test_configuration_is_plain_json(self):
        for name in ("series.json", "countries.json"):
            with (PROJECT_ROOT / "config" / name).open(encoding="utf-8") as handle:
                self.assertIsInstance(json.load(handle), list)


if __name__ == "__main__":
    unittest.main()
