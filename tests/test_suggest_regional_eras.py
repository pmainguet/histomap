import unittest

from pipeline.suggest_regional_eras import geography_matches, overlap_years, rank_candidates


class OverlapYearsTests(unittest.TestCase):
    def test_full_containment(self) -> None:
        self.assertEqual(overlap_years((500, 600), (0, 1000)), 100)

    def test_partial_overlap(self) -> None:
        self.assertEqual(overlap_years((900, 1100), (500, 1000)), 100)

    def test_no_overlap_returns_zero(self) -> None:
        self.assertEqual(overlap_years((0, 100), (200, 300)), 0)

    def test_touching_ranges_return_zero(self) -> None:
        self.assertEqual(overlap_years((0, 100), (100, 200)), 0)


class GeographyMatchesTests(unittest.TestCase):
    def test_historical_region_overlap_wins_over_shared_continent(self) -> None:
        # Same continent (asia), different historical_region -- must not match.
        source = {"continents": ["asia"], "historical_regions": ["west_asia"]}
        candidate = {"continents": ["asia"], "historical_regions": ["east_asia"]}
        self.assertFalse(geography_matches(source, candidate))

    def test_historical_region_overlap_matches(self) -> None:
        source = {"continents": ["asia"], "historical_regions": ["west_asia"]}
        candidate = {"continents": ["asia"], "historical_regions": ["west_asia"]}
        self.assertTrue(geography_matches(source, candidate))

    def test_falls_back_to_continent_when_either_side_lacks_regions(self) -> None:
        source = {"continents": ["asia"]}  # no historical_regions yet
        candidate = {"continents": ["asia"], "historical_regions": ["east_asia"]}
        self.assertTrue(geography_matches(source, candidate))

    def test_empty_candidate_continents_always_matches(self) -> None:
        source = {"continents": ["asia"], "historical_regions": ["west_asia"]}
        candidate = {"continents": []}  # macro chapter: deliberately global
        self.assertTrue(geography_matches(source, candidate))


class RankCandidatesTests(unittest.TestCase):
    def test_picks_the_best_overlap(self) -> None:
        period = {"start": 900, "end": 1000, "geography": {"continents": ["europe"]}}
        candidates = [
            {"id": "b", "start": 500, "end": 950, "geography": {"continents": ["europe"]}},
            {"id": "a", "start": 800, "end": 1100, "geography": {"continents": ["europe"]}},
        ]
        ranked = rank_candidates(period, candidates)
        self.assertEqual(ranked[0]["id"], "a")

    def test_filters_out_non_overlapping_continent(self) -> None:
        period = {"start": 900, "end": 1000, "geography": {"continents": ["asia"]}}
        candidates = [
            {"id": "a", "start": 800, "end": 1100, "geography": {"continents": ["europe"]}},
        ]
        self.assertEqual(rank_candidates(period, candidates), [])

    def test_historical_region_overlap_beats_raw_overlap_years(self) -> None:
        # Reproduces the real bug: ancient_egypt_period (africa+asia via Sinai)
        # used to rank mesopotamian_early_states_era above the correct
        # egyptian_early_states_era purely because Mesopotamia's date range
        # happened to have more raw overlap years. historical_regions fixes it.
        period = {
            "start": -3000,
            "end": -500,
            "geography": {"continents": ["africa", "asia"], "historical_regions": ["north_africa"]},
        }
        candidates = [
            {
                "id": "mesopotamian_early_states_era",
                "start": -3500,
                "end": -1200,
                "geography": {"continents": ["asia"], "historical_regions": ["west_asia"]},
            },
            {
                "id": "egyptian_early_states_era",
                "start": -3100,
                "end": -1070,
                "geography": {"continents": ["africa"], "historical_regions": ["north_africa"]},
            },
        ]
        ranked = rank_candidates(period, candidates)
        self.assertEqual([r["id"] for r in ranked], ["egyptian_early_states_era"])

    def test_ties_broken_alphabetically(self) -> None:
        period = {"start": 900, "end": 1000, "geography": {"continents": ["europe"]}}
        candidates = [
            {"id": "z_era", "start": 800, "end": 1100, "geography": {"continents": ["europe"]}},
            {"id": "a_era", "start": 800, "end": 1100, "geography": {"continents": ["europe"]}},
        ]
        ranked = rank_candidates(period, candidates)
        self.assertEqual(ranked[0]["id"], "a_era")


if __name__ == "__main__":
    unittest.main()
