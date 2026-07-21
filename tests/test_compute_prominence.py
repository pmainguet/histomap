import unittest

from pipeline.compute_prominence import balanced_visibility, prominence_components, score_prominence, tier_for


def document(entity_id: str, score: float, **overrides: object) -> dict:
    value = {
        "id": entity_id,
        "canonical_name": entity_id.replace("_", " ").title(),
        "start": 1000,
        "end": 1500,
        "entity_type": "polity",
        "entity_type_confidence": "high",
        "eligibility": "accepted",
        "geography": {"continents": ["europe"], "primary_continent": "europe"},
        "prominence_score": score,
        "prominence_components": {},
    }
    value.update(overrides)
    return value


class ComputeProminenceTests(unittest.TestCase):
    def test_components_are_capped_and_sum_to_total(self) -> None:
        components = prominence_components(
            sitelinks=100_000,
            start=-10_000,
            end=None,
            authority_coverage=50,
            historical_evidence=50,
            relationship_degree=1_000,
            transition_count=20,
            editorial_score=50,
        )
        self.assertEqual(components["wikidata_reach"], 30)
        self.assertEqual(components["authority_coverage"], 20)
        self.assertEqual(components["historical_evidence"], 20)
        self.assertEqual(components["relationship_centrality"], 15)
        self.assertEqual(components["longevity"], 8)
        self.assertEqual(components["editorial_work"], 7)
        self.assertEqual(components["total"], 100)

    def test_present_country_does_not_imply_subordination(self) -> None:
        common = dict(sitelinks=25, start=1800, end=None, authoritative=False, editorial=False)
        self.assertEqual(
            score_prominence(**common, has_parent_country=False),
            score_prominence(**common, has_parent_country=True),
        )

    def test_uncertainty_and_aggregate_penalties_are_explicit(self) -> None:
        certain = prominence_components(sitelinks=50, start=1000, end=1500)
        uncertain = prominence_components(
            sitelinks=50,
            start=1000,
            end=1500,
            entity_type_confidence="low",
            start_confidence="legendary",
            end_confidence="low",
            aggregate=True,
        )
        self.assertEqual(uncertain["type_uncertainty_penalty"], -10)
        self.assertEqual(uncertain["date_uncertainty_penalty"], -5)
        self.assertEqual(uncertain["aggregate_penalty"], -25)
        self.assertGreater(certain["total"], uncertain["total"])

    def test_balancing_represents_a_geographic_era_stratum(self) -> None:
        documents = [document(f"europe_{index}", 100 - index) for index in range(70)]
        documents.append(
            document(
                "ancient_asia",
                1,
                start=-1000,
                end=-900,
                geography={"continents": ["asia"], "primary_continent": "asia"},
            )
        )
        balanced_visibility(documents)
        self.assertEqual(documents[-1]["visibility_tier"], "global")

    def test_context_and_unreviewed_entities_are_not_automatic_global_bands(self) -> None:
        culture = document("culture", 100, entity_type="culture")
        review = document("review", 100, eligibility="review")
        low_type = document("low_type", 100, entity_type_confidence="low")
        balanced_visibility([culture, review, low_type])
        self.assertEqual(culture["visibility_tier"], "regional")
        self.assertEqual(review["visibility_tier"], "detailed")
        self.assertEqual(low_type["visibility_tier"], "detailed")

    def test_editorial_visibility_override_is_durable(self) -> None:
        item = document("overridden", 1, visibility_override="global", eligibility="review")
        balanced_visibility([item])
        self.assertEqual(item["visibility_tier"], "global")
        self.assertEqual(tier_for(10, "global"), "global")


if __name__ == "__main__":
    unittest.main()
