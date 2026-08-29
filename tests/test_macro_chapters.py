import unittest
from pathlib import Path

import yaml

from schema import Period

ROOT = Path(__file__).resolve().parents[1]
PERIODS_DIR = ROOT / "periods"

EXPECTED_IDS = [
    "macro_human_origins_paleolithic",
    "macro_agricultural_transitions",
    "macro_early_cities_states",
    "macro_classical_imperial_worlds",
    "macro_postclassical_worlds",
    "macro_early_modern_connections",
    "macro_industrial_imperial_world",
    "macro_world_wars_reordering",
    "macro_contemporary_world",
]


class MacroChapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.chapters = []
        for chapter_id in EXPECTED_IDS:
            path = PERIODS_DIR / f"{chapter_id}.yaml"
            self.assertTrue(path.exists(), f"missing {path}")
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.chapters.append(Period.model_validate(data))

    def test_all_nine_exist_with_macro_chapter_tier_and_no_parent(self) -> None:
        self.assertEqual(len(self.chapters), 9)
        for chapter in self.chapters:
            self.assertEqual(chapter.tier, "macro_chapter")
            self.assertEqual(chapter.broader_periods, [])

    def test_chapters_are_contiguous_with_no_gap_or_overlap(self) -> None:
        ordered = sorted(self.chapters, key=lambda c: c.start)
        for earlier, later in zip(ordered, ordered[1:]):
            self.assertEqual(
                earlier.end,
                later.start,
                f"{earlier.id} ends {earlier.end}, {later.id} starts {later.start}",
            )

    def test_span_covers_deep_past_to_present(self) -> None:
        ordered = sorted(self.chapters, key=lambda c: c.start)
        self.assertEqual(ordered[0].start, -3_000_000)
        self.assertEqual(ordered[-1].end, 2100)  # open-ended, modeled as YEAR_MAX

    def test_only_macro_chapters_may_have_empty_continents(self) -> None:
        for chapter in self.chapters:
            self.assertEqual(chapter.geography.continents, [])


if __name__ == "__main__":
    unittest.main()
