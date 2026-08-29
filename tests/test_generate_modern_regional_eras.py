import unittest

from pipeline.generate_modern_regional_eras import (
    MODERN_MACRO_CHAPTERS,
    combinations_with_polities,
    era_id,
)


class EraIdTests(unittest.TestCase):
    def test_builds_a_stable_id(self) -> None:
        self.assertEqual(
            era_id("europe", "macro_industrial_imperial_world"),
            "europe_industrial_imperial_world_era",
        )


class CombinationsWithPolitiesTests(unittest.TestCase):
    def test_only_combinations_with_at_least_one_polity_are_returned(self) -> None:
        polities = [
            {"start": 1850, "end": 1900, "geography": {"continents": ["europe"]}},
            {"start": 1000, "end": 1100, "geography": {"continents": ["europe"]}},  # wrong era
            {"start": 1850, "end": None, "geography": {"continents": []}},  # no geography
        ]
        combos = combinations_with_polities(polities, MODERN_MACRO_CHAPTERS)
        self.assertIn(("europe", "macro_industrial_imperial_world"), combos)
        self.assertNotIn(("unknown", "macro_industrial_imperial_world"), combos)

    def test_a_polity_spanning_two_chapters_counts_for_both(self) -> None:
        polities = [
            {"start": 1900, "end": 1950, "geography": {"continents": ["asia"]}},
        ]
        combos = combinations_with_polities(polities, MODERN_MACRO_CHAPTERS)
        self.assertIn(("asia", "macro_industrial_imperial_world"), combos)
        self.assertIn(("asia", "macro_world_wars_reordering"), combos)
        self.assertIn(("asia", "macro_contemporary_world"), combos)


if __name__ == "__main__":
    unittest.main()
