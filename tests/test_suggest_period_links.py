import unittest

from pipeline.suggest_period_links import best_period_for_polity, in_scope


class InScopeTests(unittest.TestCase):
    def test_global_tier_in_scope(self) -> None:
        self.assertTrue(in_scope({"visibility_tier": "global"}))

    def test_regional_tier_in_scope(self) -> None:
        self.assertTrue(in_scope({"visibility_tier": "regional"}))

    def test_detailed_tier_out_of_scope_without_override(self) -> None:
        self.assertFalse(in_scope({"visibility_tier": "detailed"}))

    def test_detailed_tier_with_override_in_scope(self) -> None:
        self.assertTrue(
            in_scope({"visibility_tier": "detailed", "visibility_override": "global"})
        )


class BestPeriodForPolityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.periods = [
            {
                "id": "macro_postclassical_worlds",
                "tier": "macro_chapter",
                "start": 500,
                "end": 1500,
                "geography": {"continents": []},
            },
            {
                "id": "medieval_europe_era",
                "tier": "regional_era",
                "start": 500,
                "end": 1500,
                "geography": {"continents": ["europe"]},
            },
            {
                "id": "viking_age_period",
                "tier": "period",
                "start": 793,
                "end": 1066,
                "geography": {"continents": ["europe"]},
            },
        ]

    def test_prefers_most_specific_tier_when_all_overlap(self) -> None:
        polity = {"start": 900, "end": 950, "geography": {"continents": ["europe"]}}
        best = best_period_for_polity(polity, self.periods)
        self.assertEqual(best["id"], "viking_age_period")

    def test_falls_back_to_regional_era_when_no_period_matches(self) -> None:
        polity = {"start": 1200, "end": 1300, "geography": {"continents": ["europe"]}}
        best = best_period_for_polity(polity, self.periods)
        self.assertEqual(best["id"], "medieval_europe_era")

    def test_falls_back_to_macro_chapter_when_no_geography(self) -> None:
        polity = {"start": 1200, "end": 1300, "geography": {"continents": []}}
        best = best_period_for_polity(polity, self.periods)
        self.assertEqual(best["id"], "macro_postclassical_worlds")

    def test_returns_none_when_nothing_overlaps(self) -> None:
        polity = {"start": 2000, "end": 2020, "geography": {"continents": ["europe"]}}
        self.assertIsNone(best_period_for_polity(polity, self.periods))


if __name__ == "__main__":
    unittest.main()
