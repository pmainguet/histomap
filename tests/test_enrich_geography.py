import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from pipeline.enrich_geography import (
    backfill_continents_from_present_countries,
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


class BackfillContinentsFromPresentCountriesTests(unittest.TestCase):
    """Found live, 3 September 2026: 21 records already had `present_countries`
    (and, via derive_historical_regions.py, a real `historical_region`) but
    genuinely empty `continents` -- resolve_from_centroid()'s continent half
    only ever counts when it's already among the record's own claimed
    continents, so a bare centroid resolving a NEW country could never
    complete the chain. This pass revisits present_countries directly,
    independent of any centroid."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "polities").mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_polity(self, polity_id: str, geography: dict, manual_overrides: list | None = None) -> None:
        document = {"id": polity_id, "canonical_name": polity_id, "geography": geography}
        if manual_overrides is not None:
            document["manual_overrides"] = manual_overrides
        (self.root / "polities" / f"{polity_id}.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
        )

    def test_fills_continents_from_present_countries(self) -> None:
        self.write_polity("byzantium", {"present_countries": ["TR"], "historical_regions": ["west_asia"]})
        with patch("pipeline.enrich_geography.POLITIES_DIR", self.root / "polities"), patch(
            "pipeline.seed_present_countries_from_name.load_iso2_to_continents",
            return_value={"TR": ["asia", "europe"]},
        ):
            filled = backfill_continents_from_present_countries()
        self.assertEqual(filled, 1)
        document = yaml.safe_load((self.root / "polities" / "byzantium.yaml").read_text(encoding="utf-8"))
        self.assertEqual(document["geography"]["continents"], ["asia", "europe"])

    def test_leaves_records_with_no_present_countries_untouched(self) -> None:
        self.write_polity("tang_dynasty", {})
        with patch("pipeline.enrich_geography.POLITIES_DIR", self.root / "polities"), patch(
            "pipeline.seed_present_countries_from_name.load_iso2_to_continents", return_value={},
        ):
            filled = backfill_continents_from_present_countries()
        self.assertEqual(filled, 0)

    def test_skips_a_country_missing_from_the_reverse_index(self) -> None:
        # AU/JM are present in wikidata_country_metadata.json but with empty
        # continents (an upstream Wikidata data-modeling gap) -- their ISO2
        # never makes it into load_iso2_to_continents()'s reverse index at
        # all, so this pass must silently skip rather than guess.
        self.write_polity("some_australian_micronation", {"present_countries": ["AU"]})
        with patch("pipeline.enrich_geography.POLITIES_DIR", self.root / "polities"), patch(
            "pipeline.seed_present_countries_from_name.load_iso2_to_continents", return_value={},
        ):
            filled = backfill_continents_from_present_countries()
        self.assertEqual(filled, 0)
        document = yaml.safe_load(
            (self.root / "polities" / "some_australian_micronation.yaml").read_text(encoding="utf-8")
        )
        self.assertNotIn("continents", document["geography"])

    def test_locked_geography_is_left_alone(self) -> None:
        self.write_polity(
            "manually_locked", {"present_countries": ["FR"]}, manual_overrides=["geography"],
        )
        with patch("pipeline.enrich_geography.POLITIES_DIR", self.root / "polities"), patch(
            "pipeline.seed_present_countries_from_name.load_iso2_to_continents",
            return_value={"FR": ["europe"]},
        ):
            filled = backfill_continents_from_present_countries()
        self.assertEqual(filled, 0)


if __name__ == "__main__":
    unittest.main()
