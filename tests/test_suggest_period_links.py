import unittest

from pipeline.suggest_period_links import best_period_for_polity


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

    def test_historical_region_avoids_wrong_continent_wide_match(self) -> None:
        # Reproduces the real bug: an Iraqi caliphate used to match a Chinese
        # empire period purely on sharing the "asia" tag. With both sides'
        # historical_regions populated, only the correctly-regioned candidate
        # is eligible at all.
        periods = [
            {
                "id": "chinese_empire_period",
                "tier": "period",
                "start": -219,
                "end": 1912,
                "geography": {"continents": ["asia"], "historical_regions": ["east_asia"]},
            },
            {
                "id": "islamic_caliphates_era",
                "tier": "regional_era",
                "start": 622,
                "end": 1500,
                "geography": {"continents": ["asia", "africa"], "historical_regions": ["west_asia", "north_africa"]},
            },
        ]
        polity = {
            "start": 750,
            "end": 1258,
            "geography": {"continents": ["asia"], "historical_regions": ["west_asia"]},
        }
        best = best_period_for_polity(polity, periods)
        self.assertEqual(best["id"], "islamic_caliphates_era")


if __name__ == "__main__":
    unittest.main()
