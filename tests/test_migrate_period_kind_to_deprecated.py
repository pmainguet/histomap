import tempfile
import unittest
from pathlib import Path

import yaml

from pipeline.migrate_period_kind_to_deprecated import main


class MigratePeriodKindToDeprecatedTests(unittest.TestCase):
    def test_moves_kind_into_deprecated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "periods").mkdir()
            (root / "periods" / "some_period.yaml").write_text(
                yaml.safe_dump({"id": "some_period", "kind": "historical"}),
                encoding="utf-8",
            )

            summary = main(root)

            updated = yaml.safe_load(
                (root / "periods" / "some_period.yaml").read_text(encoding="utf-8")
            )
            self.assertNotIn("kind", updated)
            self.assertEqual(updated["deprecated"]["kind"], "historical")
            self.assertEqual(summary["migrated"], 1)

    def test_preserves_an_existing_deprecated_bucket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "periods").mkdir()
            (root / "periods" / "some_period.yaml").write_text(
                yaml.safe_dump({
                    "id": "some_period", "kind": "archaeological",
                    "deprecated": {"something_else": "value"},
                }),
                encoding="utf-8",
            )

            main(root)

            updated = yaml.safe_load(
                (root / "periods" / "some_period.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual(updated["deprecated"]["kind"], "archaeological")
            self.assertEqual(updated["deprecated"]["something_else"], "value")

    def test_period_without_kind_is_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "periods").mkdir()
            (root / "periods" / "some_period.yaml").write_text(
                yaml.safe_dump({"id": "some_period"}),
                encoding="utf-8",
            )

            summary = main(root)

            updated = yaml.safe_load(
                (root / "periods" / "some_period.yaml").read_text(encoding="utf-8")
            )
            self.assertNotIn("deprecated", updated)
            self.assertEqual(summary["migrated"], 0)

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "periods").mkdir()
            period_path = root / "periods" / "some_period.yaml"
            period_path.write_text(
                yaml.safe_dump({"id": "some_period", "kind": "historical"}),
                encoding="utf-8",
            )
            before = period_path.read_text(encoding="utf-8")

            summary = main(root, dry_run=True)

            self.assertEqual(period_path.read_text(encoding="utf-8"), before)
            self.assertEqual(summary["migrated"], 1)


if __name__ == "__main__":
    unittest.main()
