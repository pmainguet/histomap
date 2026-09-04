import tempfile
import unittest
from pathlib import Path

import yaml
from pydantic import ValidationError

from build import (
    find_detail_of_cycles,
    load_civilization_period_role_sources,
    validate_entity_relationships,
    validate_transitions,
)
from schema import Geography, Period, PeriodLink, Polity, Transition


def polity(polity_id: str, entity_type: str = "polity") -> Polity:
    return Polity.model_validate(
        {
            "id": polity_id,
            "canonical_name": polity_id,
            "entity_type": entity_type,
            "start": 1,
            "end": 2,
            "start_confidence": "low",
            "end_confidence": "low",
        }
    )


def detail_polity(polity_id: str, detail_of: str | None = None) -> Polity:
    return Polity.model_validate(
        {
            "id": polity_id,
            "canonical_name": polity_id,
            "detail_of": detail_of,
            "start": 1,
            "end": 2,
            "start_confidence": "low",
            "end_confidence": "low",
        }
    )


class BuildRelationshipValidationTests(unittest.TestCase):
    def test_period_requires_ordered_dates_and_a_source(self) -> None:
        with self.assertRaises(ValidationError):
            Period.model_validate(
                {
                    "id": "bad_period",
                    "canonical_name": "Bad period",
                    "kind": "historical",
                    "start": 200,
                    "end": 100,
                    "authority": "Test",
                    "source_urls": [],
                }
            )

    def test_period_link_records_evidence(self) -> None:
        link = PeriodLink.model_validate(
            {
                "period_id": "test_period",
                "entity_id": "test_entity",
                "evidence": "derived",
                "confidence": "medium",
                "source_urls": ["https://example.test/source"],
            }
        )
        self.assertEqual(link.evidence, "derived")

    def test_acyclic_parents_pass(self) -> None:
        self.assertEqual(
            find_detail_of_cycles([detail_polity("child", "parent"), detail_polity("parent")]), []
        )

    def test_parent_cycle_is_reported_once(self) -> None:
        result = find_detail_of_cycles(
            [detail_polity("first", "second"), detail_polity("second", "first")]
        )
        self.assertEqual(result, [["first", "second"]])

    def test_single_continent_becomes_primary(self) -> None:
        self.assertEqual(Geography(continents=["africa"]).primary_continent, "africa")

    def test_primary_continent_must_be_in_continent_list(self) -> None:
        with self.assertRaises(ValidationError):
            Geography(continents=["asia"], primary_continent="europe")

    def test_split_transition_shape_and_references(self) -> None:
        transition = Transition.model_validate(
            {
                "id": "division",
                "year": 2,
                "kind": "split",
                "from": ["first"],
                "to": ["second", "third"],
                "label": "Division",
            }
        )
        validate_transitions(
            [transition], [polity("first"), polity("second"), polity("third")]
        )

    def test_transition_rejects_unknown_polity(self) -> None:
        transition = Transition.model_validate(
            {
                "id": "continuity",
                "year": 2,
                "kind": "succession",
                "from": ["first"],
                "to": ["missing"],
                "label": "Continuity",
            }
        )
        with self.assertRaisesRegex(ValueError, "unknown polity IDs: missing"):
            validate_transitions([transition], [polity("first")])

    def test_transition_rejects_impossible_date(self) -> None:
        transition = Transition.model_validate(
            {
                "id": "late_transition",
                "year": 100,
                "kind": "succession",
                "from": ["first"],
                "to": ["second"],
                "label": "Too late",
            }
        )
        with self.assertRaisesRegex(ValueError, "outside source first dates"):
            validate_transitions([transition], [polity("first"), polity("second")])

    def test_transition_rejects_cultural_endpoint(self) -> None:
        transition = Transition.model_validate(
            {
                "id": "not_political",
                "year": 2,
                "kind": "succession",
                "from": ["first"],
                "to": ["culture"],
                "label": "Cultural sequence",
            }
        )
        with self.assertRaisesRegex(ValueError, "require polity endpoints: culture"):
            validate_transitions(
                [transition], [polity("first"), polity("culture", entity_type="culture")]
            )


class DetailOfValidationTests(unittest.TestCase):
    def test_detail_of_unknown_target_is_reported(self) -> None:
        errors = validate_entity_relationships([detail_polity("child", "missing_parent")])
        self.assertIn("child: unknown detail_of target missing_parent", errors)

    def test_detail_of_chain_is_not_an_error(self) -> None:
        # Multi-level nesting is real, legitimate data (Kingdom of Castile ->
        # Crown of Castile -> Hispanic Monarchy, found live 4 September 2026)
        # -- only /explore's interactive picker guards against creating a
        # NEW one; build validation must not reject one already in the data.
        grandparent = detail_polity("grandparent")
        middle = detail_polity("middle", "grandparent")
        child = detail_polity("child", "middle")
        self.assertEqual(validate_entity_relationships([grandparent, middle, child]), [])

    def test_detail_of_valid_target_has_no_error(self) -> None:
        parent = detail_polity("parent")
        child = detail_polity("child", "parent")
        self.assertEqual(validate_entity_relationships([parent, child]), [])


class LoadCivilizationPeriodRoleSourcesTests(unittest.TestCase):
    def _write(self, directory: Path, filename: str, data: dict) -> None:
        (directory / filename).write_text(yaml.safe_dump(data), encoding="utf-8")

    def test_finds_civilization_typed_polity_promoted_to_period(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root, "ancient_egypt.yaml", {"id": "ancient_egypt", "entity_type": "civilization", "timeline_role": "period"})
            sources = load_civilization_period_role_sources(root)
            self.assertEqual(sources, {"ancient_egypt": "civilization"})

    def test_ignores_civilization_typed_polity_still_an_entity(self) -> None:
        """entity_type=civilization but NOT promoted to timeline_role=period --
        already handled directly as a polity by build_explore_tree's own
        CIVILIZATION_ENTITY_TYPES check, not this lookup."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root, "elam.yaml", {"id": "elam", "entity_type": "civilization", "timeline_role": "entity"})
            self.assertEqual(load_civilization_period_role_sources(root), {})

    def test_ignores_plain_polity_promoted_to_period(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root, "some_kingdom.yaml", {"id": "some_kingdom", "entity_type": "polity", "timeline_role": "period"})
            self.assertEqual(load_civilization_period_role_sources(root), {})


if __name__ == "__main__":
    unittest.main()
