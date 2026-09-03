"""Tests for pipeline/fix_taifa_and_saxe_geography.py -- the one-off
name-cluster fix for "Taifa of *" and "Saxe-*" records no other signal
(P17, direct P30, centroid, demonym match) can resolve."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from pipeline.fix_taifa_and_saxe_geography import main


class FixTaifaAndSaxeGeographyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "polities").mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_polity(self, polity_id: str, geography: dict) -> None:
        (self.root / "polities" / f"{polity_id}.yaml").write_text(
            yaml.safe_dump({"id": polity_id, "geography": geography}, sort_keys=False),
            encoding="utf-8",
        )

    def test_taifa_of_seville_resolves_to_spain(self) -> None:
        self.write_polity("taifa_of_seville", {})
        with patch("pipeline.fix_taifa_and_saxe_geography.POLITIES_DIR", self.root / "polities"), patch(
            "pipeline.seed_present_countries_from_name.load_iso2_to_continents",
            return_value={"ES": ["europe"]},
        ):
            result = main()
        self.assertEqual(result["fixed"], 1)
        document = yaml.safe_load((self.root / "polities" / "taifa_of_seville.yaml").read_text(encoding="utf-8"))
        self.assertEqual(document["geography"]["present_countries"], ["ES"])
        self.assertEqual(document["geography"]["continents"], ["europe"])
        self.assertIn("geography", document["manual_overrides"])

    def test_taifa_of_tavira_resolves_to_portugal_not_spain(self) -> None:
        self.write_polity("taifa_of_tavira", {})
        with patch("pipeline.fix_taifa_and_saxe_geography.POLITIES_DIR", self.root / "polities"), patch(
            "pipeline.seed_present_countries_from_name.load_iso2_to_continents",
            return_value={"PT": ["europe"]},
        ):
            main()
        document = yaml.safe_load((self.root / "polities" / "taifa_of_tavira.yaml").read_text(encoding="utf-8"))
        self.assertEqual(document["geography"]["present_countries"], ["PT"])

    def test_saxe_marksuhl_resolves_to_germany(self) -> None:
        self.write_polity("saxe_marksuhl", {})
        with patch("pipeline.fix_taifa_and_saxe_geography.POLITIES_DIR", self.root / "polities"), patch(
            "pipeline.seed_present_countries_from_name.load_iso2_to_continents",
            return_value={"DE": ["europe"]},
        ):
            main()
        document = yaml.safe_load((self.root / "polities" / "saxe_marksuhl.yaml").read_text(encoding="utf-8"))
        self.assertEqual(document["geography"]["present_countries"], ["DE"])

    def test_idempotent_when_already_corrected(self) -> None:
        self.write_polity("taifa_of_seville", {"present_countries": ["ES"], "continents": ["europe"]})
        with patch("pipeline.fix_taifa_and_saxe_geography.POLITIES_DIR", self.root / "polities"), patch(
            "pipeline.seed_present_countries_from_name.load_iso2_to_continents",
            return_value={"ES": ["europe"]},
        ):
            result = main()
        self.assertEqual(result["fixed"], 0)

    def test_records_not_in_this_dataset_are_skipped_silently(self) -> None:
        with patch("pipeline.fix_taifa_and_saxe_geography.POLITIES_DIR", self.root / "polities"), patch(
            "pipeline.seed_present_countries_from_name.load_iso2_to_continents", return_value={},
        ):
            result = main()
        self.assertEqual(result["fixed"], 0)


if __name__ == "__main__":
    unittest.main()
