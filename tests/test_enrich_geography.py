import unittest

from pipeline.enrich_geography import (
    field_locked,
    locate_near_coast,
    locate_point,
    parse_point,
    point_in_polygon,
)


class GeographyEnrichmentTests(unittest.TestCase):
    def test_manual_geography_override_is_locked(self) -> None:
        self.assertTrue(field_locked({"manual_overrides": ["geography"]}, "geography"))
        self.assertFalse(field_locked({"manual_overrides": []}, "geography"))
    def test_parse_wikidata_point(self) -> None:
        self.assertEqual(parse_point("Point(2.35 48.86)"), (2.35, 48.86))
        self.assertIsNone(parse_point(None))

    def test_point_in_polygon_and_hole(self) -> None:
        polygon = [
            [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
            [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]],
        ]
        self.assertTrue(point_in_polygon(2, 2, polygon))
        self.assertFalse(point_in_polygon(5, 5, polygon))

    def test_locate_point_reads_natural_earth_properties(self) -> None:
        features = [
            {
                "properties": {"ISO_A2_EH": "FR", "CONTINENT": "Europe"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
                },
            }
        ]
        self.assertEqual(locate_point(2, 2, features), ("FR", "europe"))

    def test_near_coast_requires_a_clear_nearby_country(self) -> None:
        features = [
            {
                "properties": {"ISO_A2_EH": "NL", "CONTINENT": "Europe"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[4, 51], [5, 51], [5, 52], [4, 52], [4, 51]]],
                },
            }
        ]
        self.assertEqual(locate_near_coast(3.8, 51.5, features), ("NL", "europe"))
        self.assertIsNone(locate_near_coast(2, 51.5, features))


if __name__ == "__main__":
    unittest.main()
