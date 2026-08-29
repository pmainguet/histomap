import unittest

from pipeline.derive_historical_regions import region_for_document


class RegionForDocumentTests(unittest.TestCase):
    def test_derives_from_present_countries(self) -> None:
        document = {"geography": {"present_countries": ["IR", "IQ"], "continents": ["asia"]}}
        self.assertEqual(region_for_document(document), ["west_asia"])

    def test_multiple_countries_can_span_multiple_regions(self) -> None:
        document = {"geography": {"present_countries": ["FR", "DE"], "continents": ["europe"]}}
        self.assertEqual(sorted(region_for_document(document)), ["western_europe"])

    def test_falls_back_to_nothing_when_country_unmapped_and_absent(self) -> None:
        document = {"geography": {"present_countries": [], "continents": ["europe"]}}
        self.assertEqual(region_for_document(document), [])

    def test_unmapped_country_is_silently_skipped_not_an_error(self) -> None:
        document = {"geography": {"present_countries": ["AQ"], "continents": ["antarctica"]}}
        self.assertEqual(region_for_document(document), [])


if __name__ == "__main__":
    unittest.main()
