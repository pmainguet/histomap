"""Tests for pipeline/migrate_parent_to_detail_of.py -- the one-off
migration retiring Polity.parent/subdivision_parent_status in favor of the
already-existing Polity.detail_of field."""
import tempfile
import unittest
from pathlib import Path

import yaml

from pipeline.migrate_parent_to_detail_of import main


class MigrateParentToDetailOfTests(unittest.TestCase):
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

    def test_parent_only_record_migrates_to_detail_of(self) -> None:
        self.write_polity("realm_of_new_zealand", {"canonical_name": "Realm of New Zealand"})
        self.write_polity("new_zealand", {
            "canonical_name": "New Zealand", "entity_type": "subdivision",
            "subdivision_parent_status": "confirmed", "parent": "realm_of_new_zealand",
        })

        summary = main(self.root)

        self.assertEqual(summary["migrated"], 1)
        migrated = yaml.safe_load(
            (self.root / "polities" / "new_zealand.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(migrated["detail_of"], "realm_of_new_zealand")
        self.assertEqual(migrated["entity_type"], "subdivision")  # untouched by this migration
        self.assertNotIn("parent", migrated)
        self.assertNotIn("subdivision_parent_status", migrated)
        self.assertEqual(migrated["deprecated"]["parent"], "realm_of_new_zealand")
        self.assertEqual(migrated["deprecated"]["subdivision_parent_status"], "confirmed")

    def test_record_with_both_fields_keeps_existing_detail_of(self) -> None:
        self.write_polity("portugal", {"canonical_name": "Portugal"})
        self.write_polity("union_kingdom", {"canonical_name": "United Kingdom of Portugal, Brazil and the Algarves"})
        self.write_polity("kingdom_of_the_algarve", {
            "canonical_name": "Kingdom of the Algarve",
            "parent": "union_kingdom", "detail_of": "portugal",
            "notes": "Automatically generated from Wikidata; requires review.",
        })

        summary = main(self.root)

        self.assertEqual(summary["kept_existing_detail_of"], 1)
        migrated = yaml.safe_load(
            (self.root / "polities" / "kingdom_of_the_algarve.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(migrated["detail_of"], "portugal")
        self.assertNotIn("parent", migrated)
        self.assertEqual(migrated["deprecated"]["parent"], "union_kingdom")
        self.assertIn("union_kingdom", migrated["notes"])
        self.assertIn("portugal", migrated["notes"])

    def test_chained_parent_target_migrates_unflattened(self) -> None:
        # Multi-level nesting is legitimate data -- the migration preserves
        # it exactly, it does not flatten a chain to a single root.
        self.write_polity("syria", {"canonical_name": "Syria"})
        self.write_polity("french_mandate_for_syria_and_the_lebanon", {
            "canonical_name": "French Mandate for Syria and the Lebanon", "detail_of": "syria",
        })
        self.write_polity("french_mandate_of_lebanon", {
            "canonical_name": "French mandate of Lebanon",
            "parent": "french_mandate_for_syria_and_the_lebanon",
        })

        main(self.root)

        migrated = yaml.safe_load(
            (self.root / "polities" / "french_mandate_of_lebanon.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(migrated["detail_of"], "french_mandate_for_syria_and_the_lebanon")
        self.assertEqual(migrated["deprecated"]["parent"], "french_mandate_for_syria_and_the_lebanon")

    def test_records_without_parent_are_untouched(self) -> None:
        self.write_polity("sweden", {"canonical_name": "Sweden", "consolidation_status": "independent"})

        summary = main(self.root)

        self.assertEqual(summary["migrated"], 0)
        untouched = yaml.safe_load((self.root / "polities" / "sweden.yaml").read_text(encoding="utf-8"))
        self.assertEqual(untouched["consolidation_status"], "independent")
        self.assertNotIn("detail_of", untouched)

    def test_dry_run_writes_nothing(self) -> None:
        self.write_polity("realm_of_new_zealand", {"canonical_name": "Realm of New Zealand"})
        self.write_polity("new_zealand", {
            "canonical_name": "New Zealand", "entity_type": "subdivision",
            "parent": "realm_of_new_zealand",
        })

        summary = main(self.root, dry_run=True)

        self.assertEqual(summary["migrated"], 1)
        untouched = yaml.safe_load(
            (self.root / "polities" / "new_zealand.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(untouched["parent"], "realm_of_new_zealand")
        self.assertNotIn("detail_of", untouched)


if __name__ == "__main__":
    unittest.main()
