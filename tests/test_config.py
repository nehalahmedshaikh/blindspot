import json
import unittest
from pathlib import Path

from blindspot.config import PROJECT_ROOT, load_countries, load_goals, load_series


class ConfigurationTests(unittest.TestCase):
    def test_series_match_goal_metadata(self):
        specs = load_series()
        goals = load_goals()
        self.assertTrue(specs)
        self.assertEqual(len({item.code for item in specs}), len(specs))
        self.assertEqual(
            {goal for item in specs for goal in (item.goals or [item.goal])},
            {item["id"] for item in goals},
        )
        indicators = [indicator for item in specs for indicator in item.indicators]
        self.assertEqual(len(indicators), len(set(indicators)))
        self.assertTrue(all(item.selection for item in specs))

    def test_country_registry_has_193_unique_members(self):
        countries = load_countries()
        self.assertTrue(countries)
        self.assertEqual(len({item.m49 for item in countries}), len(countries))
        self.assertEqual(len({item.alpha3 for item in countries}), len(countries))

    def test_configuration_is_plain_json(self):
        for name in ("series.json", "countries.json", "goals.json"):
            with (PROJECT_ROOT / "config" / name).open(encoding="utf-8") as handle:
                self.assertIsInstance(json.load(handle), list)


if __name__ == "__main__":
    unittest.main()
