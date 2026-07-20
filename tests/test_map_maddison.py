import unittest

import pandas as pd

from pipeline.map_maddison import map_document


class MaddisonMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = pd.DataFrame(
            {
                "country_code": ["FRA", "FRA", "FRA"],
                "country": ["France"] * 3,
                "year": [1490, 1600, 1700],
                "population": [1, 2, 3],
                "gdp_per_capita": [10, 20, 30],
            }
        )

    def test_maps_only_observations_during_the_polity_lifespan(self) -> None:
        document = {
            "id": "test_france",
            "canonical_name": "France",
            "external_ids": {"wikidata": "QTEST"},
            "start": 1550,
            "end": None,
            "eligibility": "accepted",
            "geography": {"present_countries": ["FR"]},
        }
        decision, result = map_document(document, self.data, {"FR": "FRA"}, {"QTEST"})
        self.assertEqual(decision, "mapped")
        self.assertEqual(result["year"].tolist(), [1600, 1700])

    def test_skips_multi_country_polities(self) -> None:
        document = {
            "id": "empire",
            "canonical_name": "Test Empire",
            "external_ids": {"wikidata": "QTEST"},
            "start": 1600,
            "end": None,
            "eligibility": "accepted",
            "geography": {"present_countries": ["FR", "DE"]},
        }
        decision, result = map_document(
            document, self.data, {"FR": "FRA", "DE": "DEU"}, {"QTEST"}
        )
        self.assertEqual(decision, "country coverage not singular")
        self.assertTrue(result.empty)

    def test_skips_pre_1500_polities(self) -> None:
        document = {
            "id": "old_state",
            "canonical_name": "Old State",
            "external_ids": {"wikidata": "QTEST"},
            "start": 1400,
            "end": 1700,
            "eligibility": "accepted",
            "geography": {"present_countries": ["FR"]},
        }
        self.assertEqual(
            map_document(document, self.data, {"FR": "FRA"}, {"QTEST"})[0],
            "pre-1500 polity",
        )

    def test_skips_historical_single_country_polities(self) -> None:
        document = {
            "id": "small_principality",
            "canonical_name": "Small Principality",
            "external_ids": {"wikidata": "QTEST"},
            "start": 1600,
            "end": 1700,
            "eligibility": "accepted",
            "geography": {"present_countries": ["DE"]},
        }
        decision, result = map_document(document, self.data, {"DE": "DEU"}, {"QTEST"})
        self.assertEqual(decision, "historical polity needs polygons")
        self.assertTrue(result.empty)

    def test_skips_entities_without_a_direct_sovereign_type(self) -> None:
        document = {
            "id": "incomplete_historical_entity",
            "canonical_name": "Incomplete Historical Entity",
            "external_ids": {"wikidata": "QOTHER"},
            "start": 1600,
            "end": None,
            "eligibility": "accepted",
            "geography": {"present_countries": ["FR"]},
        }
        decision, result = map_document(document, self.data, {"FR": "FRA"}, {"QTEST"})
        self.assertEqual(decision, "not directly sovereign")
        self.assertTrue(result.empty)


if __name__ == "__main__":
    unittest.main()
