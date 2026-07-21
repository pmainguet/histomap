import unittest

from pipeline.classify_period_roles import has_entity_branch, period_document, period_roles


class PeriodRoleClassificationTests(unittest.TestCase):
    def test_historical_period_branch_is_detected(self) -> None:
        ancestry = {"Q_specific_period": {"Q11514315": 2}}
        self.assertEqual(period_roles({"Q_specific_period"}, ancestry), ["historical"])

    def test_civilization_branch_makes_record_dual_role(self) -> None:
        ancestry = {"Q_ancient_civilization": {"Q8432": 1}}
        self.assertTrue(has_entity_branch({"Q_ancient_civilization"}, ancestry))

    def test_period_document_uses_overlay_model(self) -> None:
        value = period_document(
            {
                "id": "bronze_age",
                "canonical_name": "Bronze Age",
                "start": -3300,
                "end": -1200,
                "start_confidence": "low",
                "end_confidence": "low",
                "external_ids": {"wikidata": "Q1"},
                "geography": {"continents": ["asia"]},
            },
            ["archaeological"],
        )
        self.assertEqual(value["kind"], "archaeological")
        self.assertEqual(value["id"], "bronze_age_period")


if __name__ == "__main__":
    unittest.main()
