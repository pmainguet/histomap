import unittest

from pipeline.geography_overlap import geography_matches, overlap_years


class OverlapYearsTests(unittest.TestCase):
    def test_full_containment(self) -> None:
        self.assertEqual(overlap_years((500, 600), (0, 1000)), 100)

    def test_no_overlap_returns_zero(self) -> None:
        self.assertEqual(overlap_years((0, 100), (200, 300)), 0)


class GeographyMatchesTests(unittest.TestCase):
    def test_historical_region_overlap_wins_over_shared_continent(self) -> None:
        source = {"continents": ["asia"], "historical_regions": ["west_asia"]}
        candidate = {"continents": ["asia"], "historical_regions": ["east_asia"]}
        self.assertFalse(geography_matches(source, candidate))

    def test_falls_back_to_continent_when_either_side_lacks_regions(self) -> None:
        source = {"continents": ["asia"]}
        candidate = {"continents": ["asia"], "historical_regions": ["east_asia"]}
        self.assertTrue(geography_matches(source, candidate))

    def test_empty_candidate_continents_always_matches(self) -> None:
        source = {"continents": ["asia"], "historical_regions": ["west_asia"]}
        candidate = {"continents": []}
        self.assertTrue(geography_matches(source, candidate))


if __name__ == "__main__":
    unittest.main()
