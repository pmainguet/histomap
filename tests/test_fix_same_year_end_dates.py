"""Tests for pipeline/fix_same_year_end_dates.py -- the one-off remediation
recovering real end years for records nulled by the same-year start/end
bug fixed in pipeline/wd_to_yaml.py and schema.py."""
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import yaml

from pipeline.fix_same_year_end_dates import main


class FixSameYearEndDatesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "polities").mkdir()
        self.parquet_path = self.root / "wikidata.parquet"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_polity(self, polity_id: str, fields: dict) -> None:
        (self.root / "polities" / f"{polity_id}.yaml").write_text(
            yaml.safe_dump({"id": polity_id, **fields}, sort_keys=False), encoding="utf-8"
        )

    def write_parquet(self, rows: list[dict]) -> None:
        pd.DataFrame(rows).to_parquet(self.parquet_path)

    def test_recovers_same_year_end_date(self) -> None:
        self.write_polity("inner_mongolian_peoples_republic", {
            "canonical_name": "Inner Mongolian People's Republic",
            "external_ids": {"wikidata": "Q4120908"},
            "start": 1945, "end": None,
            "start_confidence": "low", "end_confidence": "low",
        })
        self.write_parquet([{
            "qid": "Q4120908", "inception": "+1945-09-09T00:00:00Z",
            "dissolution": "+1945-11-06T00:00:00Z",
        }])

        summary = main(self.root, self.parquet_path)

        self.assertEqual(summary["fixed"], 1)
        fixed = yaml.safe_load(
            (self.root / "polities" / "inner_mongolian_peoples_republic.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(fixed["end"], 1945)
        self.assertEqual(fixed["end_confidence"], "low")
        self.assertIn("corrected from null", fixed["notes"])

    def test_leaves_genuinely_open_ended_records_untouched(self) -> None:
        self.write_polity("spain", {
            "canonical_name": "Spain", "external_ids": {"wikidata": "Q29"},
            "start": 1516, "end": None,
            "start_confidence": "low", "end_confidence": "low",
        })
        self.write_parquet([{
            "qid": "Q29", "inception": "+1516-01-01T00:00:00Z", "dissolution": None,
        }])

        summary = main(self.root, self.parquet_path)

        self.assertEqual(summary["fixed"], 0)
        untouched = yaml.safe_load((self.root / "polities" / "spain.yaml").read_text(encoding="utf-8"))
        self.assertIsNone(untouched["end"])

    def test_leaves_genuinely_reversed_dissolution_untouched(self) -> None:
        self.write_polity("amurru_kingdom", {
            "canonical_name": "Amurru Kingdom", "external_ids": {"wikidata": "Q123456"},
            "start": 1380, "end": None,
            "start_confidence": "low", "end_confidence": "low",
        })
        self.write_parquet([{
            "qid": "Q123456", "inception": "+1380-01-01T00:00:00Z",
            "dissolution": "+1200-01-01T00:00:00Z",
        }])

        summary = main(self.root, self.parquet_path)

        self.assertEqual(summary["fixed"], 0)
        untouched = yaml.safe_load((self.root / "polities" / "amurru_kingdom.yaml").read_text(encoding="utf-8"))
        self.assertIsNone(untouched["end"])

    def test_skips_records_with_a_manual_dates_override(self) -> None:
        self.write_polity("manually_reviewed", {
            "canonical_name": "Manually Reviewed", "external_ids": {"wikidata": "Q999"},
            "start": 1918, "end": None,
            "start_confidence": "low", "end_confidence": "low",
            "manual_overrides": ["dates"],
        })
        self.write_parquet([{
            "qid": "Q999", "inception": "+1918-01-01T00:00:00Z",
            "dissolution": "+1918-06-01T00:00:00Z",
        }])

        summary = main(self.root, self.parquet_path)

        self.assertEqual(summary["fixed"], 0)
        untouched = yaml.safe_load((self.root / "polities" / "manually_reviewed.yaml").read_text(encoding="utf-8"))
        self.assertIsNone(untouched["end"])

    def test_leaves_records_with_an_already_finite_end_untouched(self) -> None:
        self.write_polity("french_first_republic", {
            "canonical_name": "French First Republic", "external_ids": {"wikidata": "Q58296"},
            "start": 1792, "end": 1804,
            "start_confidence": "low", "end_confidence": "low",
        })
        self.write_parquet([{
            "qid": "Q58296", "inception": "+1792-01-01T00:00:00Z",
            "dissolution": "+1804-01-01T00:00:00Z",
        }])

        summary = main(self.root, self.parquet_path)

        self.assertEqual(summary["fixed"], 0)
        untouched = yaml.safe_load((self.root / "polities" / "french_first_republic.yaml").read_text(encoding="utf-8"))
        self.assertEqual(untouched["end"], 1804)

    def test_dry_run_writes_nothing(self) -> None:
        self.write_polity("inner_mongolian_peoples_republic", {
            "canonical_name": "Inner Mongolian People's Republic",
            "external_ids": {"wikidata": "Q4120908"},
            "start": 1945, "end": None,
            "start_confidence": "low", "end_confidence": "low",
        })
        self.write_parquet([{
            "qid": "Q4120908", "inception": "+1945-09-09T00:00:00Z",
            "dissolution": "+1945-11-06T00:00:00Z",
        }])

        summary = main(self.root, self.parquet_path, dry_run=True)

        self.assertEqual(summary["fixed"], 1)
        untouched = yaml.safe_load(
            (self.root / "polities" / "inner_mongolian_peoples_republic.yaml").read_text(encoding="utf-8")
        )
        self.assertIsNone(untouched["end"])


if __name__ == "__main__":
    unittest.main()
