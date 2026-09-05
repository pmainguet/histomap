import tempfile
import unittest
from pathlib import Path

import yaml

from pipeline.backfill_promoted_from import main


class BackfillPromotedFromTests(unittest.TestCase):
    def test_matches_period_to_its_source_polity_by_filename_convention(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "polities").mkdir()
            (root / "periods").mkdir()
            (root / "polities" / "some_polity.yaml").write_text(
                yaml.safe_dump({"id": "some_polity", "timeline_role": "period"}),
                encoding="utf-8",
            )
            (root / "periods" / "some_polity_period.yaml").write_text(
                yaml.safe_dump({"id": "some_polity_period", "canonical_name": "Some Polity"}),
                encoding="utf-8",
            )

            summary = main(root)

            updated = yaml.safe_load(
                (root / "periods" / "some_polity_period.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual(updated["promoted_from"], "some_polity")
            self.assertEqual(summary["backfilled"], 1)

    def test_period_without_a_timeline_role_period_source_is_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "polities").mkdir()
            (root / "periods").mkdir()
            (root / "periods" / "hand_authored_period.yaml").write_text(
                yaml.safe_dump({"id": "hand_authored_period", "canonical_name": "Hand Authored"}),
                encoding="utf-8",
            )

            summary = main(root)

            updated = yaml.safe_load(
                (root / "periods" / "hand_authored_period.yaml").read_text(encoding="utf-8")
            )
            self.assertNotIn("promoted_from", updated)
            self.assertEqual(summary["backfilled"], 0)

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "polities").mkdir()
            (root / "periods").mkdir()
            (root / "polities" / "some_polity.yaml").write_text(
                yaml.safe_dump({"id": "some_polity", "timeline_role": "period"}),
                encoding="utf-8",
            )
            period_path = root / "periods" / "some_polity_period.yaml"
            period_path.write_text(
                yaml.safe_dump({"id": "some_polity_period", "canonical_name": "Some Polity"}),
                encoding="utf-8",
            )
            before = period_path.read_text(encoding="utf-8")

            summary = main(root, dry_run=True)

            self.assertEqual(period_path.read_text(encoding="utf-8"), before)
            self.assertEqual(summary["backfilled"], 1)


if __name__ == "__main__":
    unittest.main()
