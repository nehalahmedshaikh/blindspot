import hashlib
import json
import unittest
from pathlib import Path

from blindspot.config import PROJECT_ROOT


class SiteContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = PROJECT_ROOT / "site"
        cls.data = cls.site / "assets" / "data"
        cls.meta = json.loads((cls.data / "meta.json").read_text())
        cls.countries = json.loads((cls.data / "countries.json").read_text())
        cls.series = json.loads((cls.data / "series.json").read_text())
        cls.rankings = json.loads((cls.data / "rankings.json").read_text())
        cls.indicators = json.loads((cls.data / "indicators.json").read_text())

    def test_six_focused_pages_exist(self):
        pages = ["index.html", "explore/index.html", "indicators/index.html", "research/index.html", "methods/index.html", "data/index.html"]
        for page in pages:
            self.assertTrue((self.site / page).is_file(), page)

    def test_country_files_and_goal_summaries_are_complete(self):
        country_codes = {item["alpha3"] for item in self.countries}
        published_codes = {path.stem for path in (self.data / "countries").glob("*.json")}
        self.assertEqual(published_codes, country_codes)
        for country in self.countries:
            rows = json.loads((self.data / country["data_file"]).read_text())
            self.assertEqual(len(rows), len(self.series))
            self.assertEqual({row["country_alpha3"] for row in rows}, {country["alpha3"]})
        goal_files = sorted((self.data / "goals").glob("*.json"))
        goals = json.loads((self.data / "goals.json").read_text())
        self.assertEqual(len(goal_files), len(goals))
        for path in goal_files:
            payload = json.loads(path.read_text())
            self.assertTrue(set(payload) <= country_codes)

    def test_every_official_indicator_has_one_representative(self):
        ids = [item["id"] for item in self.indicators]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), self.meta["counts"]["indicators"])
        self.assertTrue(all(item["representative"]["code"] for item in self.indicators))
        self.assertTrue(all(item["variants"] for item in self.indicators))

    def test_interactive_ranking_contains_every_ranked_pair(self):
        expected = self.meta["counts"]["countries"] * self.meta["counts"]["universal_series"]
        self.assertEqual(len(self.rankings["rows"]), expected)
        self.assertEqual(
            self.rankings["fields"],
            ["country_alpha3", "series_code", "latest_year", "staleness", "missingness", "global_scarcity", "population"],
        )

    def test_site_uses_partitioned_contract(self):
        self.assertFalse((self.data / "dashboard.json").exists())
        self.assertFalse((self.data / "index.json").exists())
        self.assertFalse((self.data / "model.json").exists())
        self.assertEqual(self.meta["counts"]["countries"], len(self.countries))
        self.assertEqual(self.meta["counts"]["series"], len(self.series))
        self.assertEqual(len(list((self.data / "countries").glob("*.json"))), len(self.countries))

    def test_research_and_glossary_are_data_driven(self):
        analysis = json.loads((self.data / "analysis.json").read_text())
        method = json.loads((self.data / "methodology.json").read_text())
        self.assertNotIn("findings", analysis)
        self.assertNotIn("supporting_results", analysis)
        self.assertEqual(len(analysis["country_distribution"]), self.meta["counts"]["countries"])
        self.assertEqual(analysis["design"]["official_indicators"], self.meta["counts"]["indicators"])
        self.assertTrue(analysis["income_goal_matrix"])
        self.assertTrue(analysis["reporting_status"])
        self.assertTrue(analysis["disaggregation_by_goal"])
        self.assertTrue(all(item.get("ci_low") is not None for item in analysis["sensitivity"]))
        self.assertEqual(analysis["pair_model"]["clusters"], self.meta["counts"]["countries"])
        self.assertEqual(analysis["context_model"]["clusters"], self.meta["counts"]["statistical_performance_countries"])
        self.assertGreater(analysis["context_model"]["clusters"], 150)
        specifications = {item["specification"] for item in analysis["sensitivity"]}
        self.assertEqual(len(specifications), 5)
        self.assertIn("Countries weighted by population", specifications)
        self.assertIn("Country-reported statuses only", specifications)
        terms = {item["term"] for item in method["glossary"]}
        self.assertTrue({"Adjusted comparison", "Bootstrap interval", "Measurement priority", "Missingness"} <= terms)

    def test_published_snapshot_ids_match(self):
        manifest = json.loads((self.data / "manifest.json").read_text())
        analysis = json.loads((self.data / "analysis.json").read_text())
        snapshot_id = manifest["snapshot_id"]
        expected = hashlib.sha256(
            json.dumps(
                [(item["source"], item["sha256"]) for item in manifest["sources"]],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()[:16]
        self.assertEqual(snapshot_id, expected)
        self.assertEqual(self.meta["meta"]["snapshot_id"], snapshot_id)
        self.assertEqual(analysis["snapshot"]["snapshot_id"], snapshot_id)

    def test_published_checksums_match(self):
        checksums = json.loads((self.data / "checksums.json").read_text())
        for relative, expected in checksums.items():
            actual = hashlib.sha256((self.data / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative)


if __name__ == "__main__":
    unittest.main()
