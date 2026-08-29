import unittest

from pipeline.historical_regions import HISTORICAL_REGIONS, historical_region_for_country


class HistoricalRegionForCountryTests(unittest.TestCase):
    def test_known_country_resolves(self) -> None:
        self.assertEqual(historical_region_for_country("IR"), "west_asia")
        self.assertEqual(historical_region_for_country("PE"), "andes")
        self.assertEqual(historical_region_for_country("MX"), "mesoamerica")

    def test_unknown_country_returns_none(self) -> None:
        self.assertIsNone(historical_region_for_country("ZZ"))

    def test_every_country_code_maps_to_exactly_one_region(self) -> None:
        seen: dict[str, str] = {}
        for region_id, countries in HISTORICAL_REGIONS.items():
            for country in countries:
                self.assertNotIn(
                    country, seen, f"{country} assigned to both {seen.get(country)} and {region_id}"
                )
                seen[country] = region_id


if __name__ == "__main__":
    unittest.main()
