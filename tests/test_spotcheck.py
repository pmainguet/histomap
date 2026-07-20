import unittest

from pipeline.spotcheck import EXPECTED, assess


class PhaseTwoSpotcheckTests(unittest.TestCase):
    def test_complete_record_passes(self) -> None:
        expected = EXPECTED[0]
        document = {
            "start": -2334,
            "end": -2154,
            "eligibility": "accepted",
            "external_ids": {"seshat": ["IqAkkad"]},
            "geography": {"continents": ["asia"], "present_countries": ["IQ"]},
        }
        self.assertEqual(assess(document, expected), ([], []))

    def test_missing_optional_coverage_is_only_a_warning(self) -> None:
        expected = EXPECTED[0]
        document = {
            "start": -2334,
            "end": -2154,
            "eligibility": "accepted",
            "external_ids": {},
            "geography": {"continents": ["asia"], "present_countries": []},
        }
        failures, warnings = assess(document, expected)
        self.assertEqual(failures, [])
        self.assertEqual(warnings, ["no present country", "not linked to Seshat"])

    def test_bad_editorial_state_and_geography_fail(self) -> None:
        expected = EXPECTED[0]
        document = {
            "start": -1000,
            "end": -900,
            "eligibility": "review",
            "external_ids": {},
            "geography": {"continents": [], "present_countries": []},
        }
        failures, _ = assess(document, expected)
        self.assertIn("not accepted", failures)
        self.assertIn("start outside baseline", failures)
        self.assertIn("missing asia geography", failures)


if __name__ == "__main__":
    unittest.main()
