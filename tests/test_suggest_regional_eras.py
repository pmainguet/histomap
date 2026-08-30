import unittest

from pipeline.suggest_regional_eras import rank_candidates


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
