import unittest

from pipeline.suggest_regional_eras import overlap_years, rank_candidates


class OverlapYearsTests(unittest.TestCase):
    def test_full_containment(self) -> None:
        self.assertEqual(overlap_years((500, 600), (0, 1000)), 100)

    def test_partial_overlap(self) -> None:
        self.assertEqual(overlap_years((900, 1100), (500, 1000)), 100)

    def test_no_overlap_returns_zero(self) -> None:
        self.assertEqual(overlap_years((0, 100), (200, 300)), 0)

    def test_touching_ranges_return_zero(self) -> None:
        self.assertEqual(overlap_years((0, 100), (100, 200)), 0)


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
