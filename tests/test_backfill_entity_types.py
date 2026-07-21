import unittest

from pipeline.backfill_entity_types import (
    classify_direct_types,
    classify_entity,
    classify_automated_entity,
    classify_inherited_types,
    effective_direct_types,
    normalized_relationship_kind,
    relationship_kind,
)


class EntityTypeBackfillTests(unittest.TestCase):
    def test_administrative_subdivision_is_a_distinct_type(self) -> None:
        result = classify_direct_types({"Q56061"})

        self.assertEqual(result[:3], ("subdivision", "high", ["Q56061"]))

    def test_manual_polity_can_still_be_a_subdivision_candidate(self) -> None:
        document = {
            "entity_type": "polity",
            "manual_overrides": ["entity_type"],
            "external_ids": {"wikidata": "Q_entity"},
        }
        cache = {"Q_entity": {"claims": [{"qid": "Q_specific", "rank": "normal"}]}}
        ancestry = {"Q_specific": {"Q56061": 1}}

        self.assertEqual(classify_entity(document, cache, ancestry)[0], "polity")
        self.assertEqual(
            classify_automated_entity(document, cache, ancestry)[:2],
            ("subdivision", "medium"),
        )
    def test_micronation_is_a_distinct_high_confidence_type(self) -> None:
        result = classify_direct_types({"Q188443"})

        self.assertEqual(result[:3], ("micronation", "high", ["Q188443"]))

    def test_direct_archaeological_type_is_high_confidence(self) -> None:
        self.assertEqual(
            classify_direct_types({"Q465299"}),
            ("culture", "high", ["Q465299"], "direct Wikidata P31"),
        )

    def test_dynastic_state_is_high_confidence_polity(self) -> None:
        self.assertEqual(
            classify_direct_types({"Q50068795"}),
            ("polity", "high", ["Q50068795"], "direct Wikidata P31"),
        )

    def test_preferred_rank_supersedes_normal_rank(self) -> None:
        metadata = {
            "types": ["legacy-value-is-ignored"],
            "claims": [
                {"qid": "Q50068795", "rank": "preferred"},
                {"qid": "Q465299", "rank": "normal"},
            ],
        }
        self.assertEqual(effective_direct_types(metadata), {"Q50068795"})

    def test_deprecated_rank_is_ignored(self) -> None:
        metadata = {
            "claims": [
                {"qid": "Q465299", "rank": "deprecated"},
                {"qid": "Q50068795", "rank": "normal"},
            ],
        }
        self.assertEqual(effective_direct_types(metadata), {"Q50068795"})

    def test_legacy_cache_types_remain_supported(self) -> None:
        self.assertEqual(effective_direct_types({"types": ["Q6256"]}), {"Q6256"})

    def test_conflicting_types_are_queued_at_medium_confidence(self) -> None:
        result = classify_direct_types({"Q3024240", "Q8432"})
        self.assertEqual(result[0], "civilization")
        self.assertEqual(result[1], "medium")

    def test_seshat_defaults_to_reviewable_polity(self) -> None:
        result = classify_entity({"external_ids": {"seshat": ["X"]}}, {})
        self.assertEqual(result[:2], ("polity", "medium"))

    def test_civilization_subclass_is_medium_confidence_civilization(self) -> None:
        result = classify_inherited_types(
            {"Q_specific_civilization"},
            {"Q_specific_civilization": {"Q8432": 2}},
        )
        self.assertEqual(result[:3], ("civilization", "medium", ["Q_specific_civilization"]))

    def test_nearest_mapped_ancestor_wins(self) -> None:
        result = classify_inherited_types(
            {"Q_specific"},
            {"Q_specific": {"Q8432": 1, "Q6256": 3}},
        )
        self.assertEqual(result[0], "civilization")

    def test_inherited_civilization_supersedes_generic_direct_polity(self) -> None:
        document = {"external_ids": {"wikidata": "Q_entity"}}
        cache = {
            "Q_entity": {
                "claims": [
                    {"qid": "Q3024240", "rank": "normal"},
                    {"qid": "Q_specific_civilization", "rank": "normal"},
                ]
            }
        }
        ancestry = {"Q_specific_civilization": {"Q8432": 1}}
        result = classify_entity(document, cache, ancestry)
        self.assertEqual(result[:2], ("civilization", "medium"))

    def test_preferred_direct_polity_excludes_normal_civilization_branch(self) -> None:
        document = {"external_ids": {"wikidata": "Q_entity"}}
        cache = {
            "Q_entity": {
                "claims": [
                    {"qid": "Q3024240", "rank": "preferred"},
                    {"qid": "Q_specific_civilization", "rank": "normal"},
                ]
            }
        }
        ancestry = {"Q_specific_civilization": {"Q8432": 1}}
        result = classify_entity(document, cache, ancestry)
        self.assertEqual(result[0], "polity")

    def test_conflicting_nearest_ancestors_are_low_confidence(self) -> None:
        result = classify_inherited_types(
            {"Q_specific"},
            {"Q_specific": {"Q8432": 1, "Q6256": 1}},
        )
        self.assertEqual(result[1], "low")

    def test_relationship_kind_separates_political_and_archaeological_succession(self) -> None:
        self.assertEqual(relationship_kind("polity", "polity", "successor"), "political_successor")
        self.assertEqual(
            relationship_kind("culture", "archaeological_horizon", "successor"),
            "archaeological_sequence",
        )

    def test_existing_relationship_is_remapped_after_type_change(self) -> None:
        self.assertEqual(
            normalized_relationship_kind("civilization", "polity", "political_successor"),
            "cultural_sequence",
        )
        self.assertEqual(
            normalized_relationship_kind("polity", "polity", "cultural_sequence"),
            "political_successor",
        )


if __name__ == "__main__":
    unittest.main()
