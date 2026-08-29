import unittest
from pathlib import Path

import yaml

from pipeline.seed_regional_eras import REGIONAL_ERAS
from schema import Period

ROOT = Path(__file__).resolve().parents[1]
PERIODS_DIR = ROOT / "periods"
VALID_MACRO_CHAPTERS = {
    "macro_human_origins_paleolithic",
    "macro_agricultural_transitions",
    "macro_early_cities_states",
    "macro_classical_imperial_worlds",
    "macro_postclassical_worlds",
}


class SeedRegionalErasTests(unittest.TestCase):
    def test_table_has_twenty_rows(self) -> None:
        self.assertEqual(len(REGIONAL_ERAS), 20)

    def test_every_row_points_at_a_pre_1500_macro_chapter(self) -> None:
        for row in REGIONAL_ERAS:
            self.assertIn(row["broader_periods"][0], VALID_MACRO_CHAPTERS)

    def test_every_row_has_exactly_one_parent(self) -> None:
        for row in REGIONAL_ERAS:
            self.assertEqual(len(row["broader_periods"]), 1)

    def test_ids_are_unique(self) -> None:
        ids = [row["id"] for row in REGIONAL_ERAS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_files_exist_and_validate_after_running(self) -> None:
        for row in REGIONAL_ERAS:
            path = PERIODS_DIR / f"{row['id']}.yaml"
            self.assertTrue(path.exists(), f"missing {path}; run the seed script")
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            period = Period.model_validate(data)
            self.assertEqual(period.tier, "regional_era")


if __name__ == "__main__":
    unittest.main()
