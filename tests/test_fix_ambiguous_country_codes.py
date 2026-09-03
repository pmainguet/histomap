"""Tests for pipeline/fix_ambiguous_country_codes.py -- the one-off
remediation for records left with an ambiguous (SU/CS) or simply wrong
(kingdom_of_tonga's TV) present_countries code."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from pipeline.fix_ambiguous_country_codes import main


class FixAmbiguousCountryCodesTests(unittest.TestCase):
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

    def test_corrects_ambiguous_soviet_code_and_locks_it(self) -> None:
        self.write_polity("moldavian_soviet_socialist_republic", {"present_countries": ["SU"]})
        with patch("pipeline.fix_ambiguous_country_codes.POLITIES_DIR", self.root / "polities"), patch(
            "pipeline.seed_present_countries_from_name.load_iso2_to_continents",
            return_value={"MD": ["europe"]},
        ):
            result = main()
        self.assertEqual(result["fixed"], 1)
        document = yaml.safe_load(
            (self.root / "polities" / "moldavian_soviet_socialist_republic.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(document["geography"]["present_countries"], ["MD"])
        self.assertEqual(document["geography"]["continents"], ["europe"])
        self.assertIn("geography", document["manual_overrides"])

    def test_corrects_tonga_mistagged_as_tuvalu(self) -> None:
        self.write_polity("kingdom_of_tonga", {"present_countries": ["TV"]})
        with patch("pipeline.fix_ambiguous_country_codes.POLITIES_DIR", self.root / "polities"), patch(
            "pipeline.seed_present_countries_from_name.load_iso2_to_continents",
            return_value={"TO": ["oceania"]},
        ):
            result = main()
        self.assertEqual(result["fixed"], 1)
        document = yaml.safe_load((self.root / "polities" / "kingdom_of_tonga.yaml").read_text(encoding="utf-8"))
        self.assertEqual(document["geography"]["present_countries"], ["TO"])

    def test_idempotent_when_already_corrected(self) -> None:
        self.write_polity(
            "kingdom_of_tonga", {"present_countries": ["TO"], "continents": ["oceania"]}
        )
        with patch("pipeline.fix_ambiguous_country_codes.POLITIES_DIR", self.root / "polities"), patch(
            "pipeline.seed_present_countries_from_name.load_iso2_to_continents",
            return_value={"TO": ["oceania"]},
        ):
            result = main()
        self.assertEqual(result["fixed"], 0)

    def test_records_not_in_this_dataset_are_skipped_silently(self) -> None:
        # No polities directory content at all -- every CORRECTIONS entry's
        # path.exists() check should just skip, not raise.
        with patch("pipeline.fix_ambiguous_country_codes.POLITIES_DIR", self.root / "polities"), patch(
            "pipeline.seed_present_countries_from_name.load_iso2_to_continents", return_value={},
        ):
            result = main()
        self.assertEqual(result["fixed"], 0)


if __name__ == "__main__":
    unittest.main()
