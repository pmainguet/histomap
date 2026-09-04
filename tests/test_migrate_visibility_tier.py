"""Tests for pipeline/migrate_visibility_tier.py -- the one-off migration
retiring Polity.visibility_tier/visibility_override, preserving old values
under deprecated."""
import tempfile
import unittest
from pathlib import Path

import yaml

from pipeline.migrate_visibility_tier import main


class MigrateVisibilityTierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "polities").mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_polity(self, polity_id: str, fields: dict) -> None:
        (self.root / "polities" / f"{polity_id}.yaml").write_text(
            yaml.safe_dump({"id": polity_id, **fields}, sort_keys=False), encoding="utf-8"
        )

    def test_tier_only_record_moves_to_deprecated(self) -> None:
        self.write_polity("sweden", {"canonical_name": "Sweden", "visibility_tier": "regional"})

        summary = main(self.root)

        self.assertEqual(summary["migrated"], 1)
        migrated = yaml.safe_load(
            (self.root / "polities" / "sweden.yaml").read_text(encoding="utf-8")
        )
        self.assertNotIn("visibility_tier", migrated)
        self.assertEqual(migrated["deprecated"]["visibility_tier"], "regional")

    def test_tier_and_override_both_move_to_deprecated(self) -> None:
        self.write_polity("nazi_germany", {
            "canonical_name": "Nazi Germany",
            "visibility_tier": "detailed", "visibility_override": "global",
        })

        main(self.root)

        migrated = yaml.safe_load(
            (self.root / "polities" / "nazi_germany.yaml").read_text(encoding="utf-8")
        )
        self.assertNotIn("visibility_tier", migrated)
        self.assertNotIn("visibility_override", migrated)
        self.assertEqual(migrated["deprecated"]["visibility_tier"], "detailed")
        self.assertEqual(migrated["deprecated"]["visibility_override"], "global")

    def test_existing_deprecated_bucket_is_preserved_and_extended(self) -> None:
        self.write_polity("crown_of_castile", {
            "canonical_name": "Crown of Castile",
            "visibility_tier": "global",
            "deprecated": {"parent": "hispanic_monarchy"},
        })

        main(self.root)

        migrated = yaml.safe_load(
            (self.root / "polities" / "crown_of_castile.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(migrated["deprecated"]["parent"], "hispanic_monarchy")
        self.assertEqual(migrated["deprecated"]["visibility_tier"], "global")

    def test_records_without_either_field_are_untouched(self) -> None:
        self.write_polity("no_tier", {"canonical_name": "No Tier", "consolidation_status": "independent"})

        summary = main(self.root)

        self.assertEqual(summary["migrated"], 0)
        untouched = yaml.safe_load((self.root / "polities" / "no_tier.yaml").read_text(encoding="utf-8"))
        self.assertEqual(untouched["consolidation_status"], "independent")
        self.assertNotIn("deprecated", untouched)

    def test_dry_run_writes_nothing(self) -> None:
        self.write_polity("sweden", {"canonical_name": "Sweden", "visibility_tier": "regional"})

        summary = main(self.root, dry_run=True)

        self.assertEqual(summary["migrated"], 1)
        untouched = yaml.safe_load(
            (self.root / "polities" / "sweden.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(untouched["visibility_tier"], "regional")
        self.assertNotIn("deprecated", untouched)


if __name__ == "__main__":
    unittest.main()
