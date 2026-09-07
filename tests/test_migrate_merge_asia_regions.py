import tempfile
import unittest
from pathlib import Path

import yaml

from pipeline.migrate_merge_asia_regions import main


class MigrateMergeAsiaRegionsTests(unittest.TestCase):
    def test_moves_south_asia_into_east_asia(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "polities").mkdir()
            (root / "periods").mkdir()
            (root / "polities" / "some_polity.yaml").write_text(
                yaml.safe_dump({
                    "id": "some_polity",
                    "geography": {
                        "historical_regions": ["south_asia"],
                        "primary_historical_region": "south_asia",
                    },
                }),
                encoding="utf-8",
            )

            summary = main(root)

            updated = yaml.safe_load(
                (root / "polities" / "some_polity.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual(updated["geography"]["historical_regions"], ["east_asia"])
            self.assertEqual(updated["geography"]["primary_historical_region"], "east_asia")
            self.assertEqual(summary["polities_migrated"], 1)
            self.assertEqual(summary["periods_migrated"], 0)

    def test_moves_southeast_asia_into_east_asia(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "polities").mkdir()
            (root / "periods").mkdir()
            (root / "periods" / "some_period.yaml").write_text(
                yaml.safe_dump({
                    "id": "some_period",
                    "geography": {
                        "historical_regions": ["southeast_asia"],
                        "primary_historical_region": "southeast_asia",
                    },
                }),
                encoding="utf-8",
            )

            summary = main(root)

            updated = yaml.safe_load(
                (root / "periods" / "some_period.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual(updated["geography"]["historical_regions"], ["east_asia"])
            self.assertEqual(updated["geography"]["primary_historical_region"], "east_asia")
            self.assertEqual(summary["periods_migrated"], 1)

    def test_dedupes_when_east_asia_already_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "polities").mkdir()
            (root / "periods").mkdir()
            (root / "polities" / "some_polity.yaml").write_text(
                yaml.safe_dump({
                    "id": "some_polity",
                    "geography": {
                        "historical_regions": ["east_asia", "south_asia"],
                        "primary_historical_region": "east_asia",
                    },
                }),
                encoding="utf-8",
            )

            main(root)

            updated = yaml.safe_load(
                (root / "polities" / "some_polity.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual(updated["geography"]["historical_regions"], ["east_asia"])

    def test_untouched_regions_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "polities").mkdir()
            (root / "periods").mkdir()
            (root / "polities" / "some_polity.yaml").write_text(
                yaml.safe_dump({
                    "id": "some_polity",
                    "geography": {
                        "historical_regions": ["west_asia", "south_asia"],
                        "primary_historical_region": "south_asia",
                    },
                }),
                encoding="utf-8",
            )

            main(root)

            updated = yaml.safe_load(
                (root / "polities" / "some_polity.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual(updated["geography"]["historical_regions"], ["east_asia", "west_asia"])
            self.assertEqual(updated["geography"]["primary_historical_region"], "east_asia")

    def test_record_without_retired_regions_is_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "polities").mkdir()
            (root / "periods").mkdir()
            (root / "polities" / "some_polity.yaml").write_text(
                yaml.safe_dump({
                    "id": "some_polity",
                    "geography": {
                        "historical_regions": ["west_asia"],
                        "primary_historical_region": "west_asia",
                    },
                }),
                encoding="utf-8",
            )

            summary = main(root)

            self.assertEqual(summary["polities_migrated"], 0)

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "polities").mkdir()
            (root / "periods").mkdir()
            polity_path = root / "polities" / "some_polity.yaml"
            polity_path.write_text(
                yaml.safe_dump({
                    "id": "some_polity",
                    "geography": {
                        "historical_regions": ["south_asia"],
                        "primary_historical_region": "south_asia",
                    },
                }),
                encoding="utf-8",
            )
            before = polity_path.read_text(encoding="utf-8")

            summary = main(root, dry_run=True)

            self.assertEqual(polity_path.read_text(encoding="utf-8"), before)
            self.assertEqual(summary["polities_migrated"], 1)


if __name__ == "__main__":
    unittest.main()
