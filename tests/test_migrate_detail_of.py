"""Tests for pipeline/migrate_detail_of.py -- the one-off migration from
phase_of/part_of consolidation_status to the unified detail_of field."""
import tempfile
import unittest
from pathlib import Path

import yaml

from pipeline.migrate_detail_of import main


class MigrateDetailOfTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "polities").mkdir()
        (self.root / "periods").mkdir()
        (self.root / "period_links.yaml").write_text("[]\n", encoding="utf-8")
        (self.root / "period_links.json").write_text("[]", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_polity(self, polity_id: str, fields: dict) -> None:
        (self.root / "polities" / f"{polity_id}.yaml").write_text(
            yaml.safe_dump({"id": polity_id, **fields}, sort_keys=False), encoding="utf-8"
        )

    def test_migrates_phase_of_record_back_to_a_live_polity(self) -> None:
        self.write_polity("spain", {
            "canonical_name": "Spain", "start": 1516, "end": None,
            "start_confidence": "low", "end_confidence": "low",
        })
        self.write_polity("francoist_spain", {
            "canonical_name": "Francoist Spain", "start": 1939, "end": 1975,
            "start_confidence": "low", "end_confidence": "low",
            "timeline_role": "retired", "consolidation_status": "phase_of",
            "consolidated_into": "spain",
        })
        (self.root / "periods" / "francoist_spain_period.yaml").write_text(
            yaml.safe_dump({
                "id": "francoist_spain_period", "canonical_name": "Francoist Spain",
                "kind": "historical", "start": 1939, "end": 1975,
                "start_confidence": "low", "end_confidence": "low",
                "geography": {}, "broader_periods": [], "successors": [],
                "authority": "Histomap editorial consolidation",
                "external_ids": {}, "notes": "", "source_urls": [],
            }, sort_keys=False), encoding="utf-8",
        )
        (self.root / "period_links.yaml").write_text(yaml.safe_dump([
            {"period_id": "francoist_spain_period", "entity_id": "spain",
             "relation": "phase_of", "source_urls": [], "notes": ""},
        ]), encoding="utf-8")

        summary = main(self.root)

        self.assertEqual(summary["migrated_phase_of"], 1)
        migrated = yaml.safe_load(
            (self.root / "polities" / "francoist_spain.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(migrated["detail_of"], "spain")
        self.assertEqual(migrated["timeline_role"], "entity")
        self.assertNotIn("consolidation_status", migrated)
        self.assertNotIn("consolidated_into", migrated)
        self.assertEqual(migrated["deprecated"]["consolidation_status"], "phase_of")
        self.assertEqual(migrated["deprecated"]["consolidated_into"], "spain")
        self.assertEqual(migrated["deprecated"]["period"]["id"], "francoist_spain_period")
        self.assertEqual(migrated["deprecated"]["period_link"]["relation"], "phase_of")
        self.assertFalse((self.root / "periods" / "francoist_spain_period.yaml").exists())
        remaining_links = yaml.safe_load((self.root / "period_links.yaml").read_text(encoding="utf-8"))
        self.assertEqual(remaining_links, [])

    def test_migrates_part_of_record_and_reverts_entity_type(self) -> None:
        self.write_polity("realm_of_new_zealand", {
            "canonical_name": "Realm of New Zealand", "start": 1983, "end": None,
            "start_confidence": "low", "end_confidence": "low",
        })
        self.write_polity("new_zealand", {
            "canonical_name": "New Zealand", "start": 1841, "end": None,
            "start_confidence": "low", "end_confidence": "low",
            "entity_type": "subdivision", "subdivision_parent_status": "confirmed",
            "parent": "realm_of_new_zealand", "consolidation_status": "part_of",
        })

        summary = main(self.root)

        self.assertEqual(summary["migrated_part_of"], 1)
        migrated = yaml.safe_load(
            (self.root / "polities" / "new_zealand.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(migrated["detail_of"], "realm_of_new_zealand")
        self.assertEqual(migrated["entity_type"], "polity")
        self.assertNotIn("parent", migrated)
        self.assertNotIn("subdivision_parent_status", migrated)
        self.assertNotIn("consolidation_status", migrated)
        self.assertEqual(migrated["deprecated"]["parent"], "realm_of_new_zealand")
        self.assertEqual(migrated["deprecated"]["entity_type"], "subdivision")

    def test_leaves_independent_and_same_entity_records_untouched(self) -> None:
        self.write_polity("sweden", {
            "canonical_name": "Sweden", "start": 1523, "end": None,
            "start_confidence": "low", "end_confidence": "low",
            "consolidation_status": "independent",
        })

        summary = main(self.root)

        self.assertEqual(summary["migrated_phase_of"], 0)
        self.assertEqual(summary["migrated_part_of"], 0)
        untouched = yaml.safe_load((self.root / "polities" / "sweden.yaml").read_text(encoding="utf-8"))
        self.assertEqual(untouched["consolidation_status"], "independent")
        self.assertNotIn("detail_of", untouched)

    def test_dry_run_writes_nothing(self) -> None:
        self.write_polity("spain", {
            "canonical_name": "Spain", "start": 1516, "end": None,
            "start_confidence": "low", "end_confidence": "low",
        })
        self.write_polity("francoist_spain", {
            "canonical_name": "Francoist Spain", "start": 1939, "end": 1975,
            "start_confidence": "low", "end_confidence": "low",
            "timeline_role": "retired", "consolidation_status": "phase_of",
            "consolidated_into": "spain",
        })
        (self.root / "periods" / "francoist_spain_period.yaml").write_text(
            yaml.safe_dump({
                "id": "francoist_spain_period", "canonical_name": "Francoist Spain",
                "kind": "historical", "start": 1939, "end": 1975,
                "start_confidence": "low", "end_confidence": "low",
                "geography": {}, "broader_periods": [], "successors": [],
                "authority": "x", "external_ids": {}, "notes": "", "source_urls": [],
            }, sort_keys=False), encoding="utf-8",
        )

        summary = main(self.root, dry_run=True)

        self.assertEqual(summary["migrated_phase_of"], 1)
        untouched = yaml.safe_load(
            (self.root / "polities" / "francoist_spain.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(untouched["consolidation_status"], "phase_of")
        self.assertTrue((self.root / "periods" / "francoist_spain_period.yaml").exists())


if __name__ == "__main__":
    unittest.main()
