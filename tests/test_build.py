import unittest

from build import find_parent_cycles, validate_transitions
from pydantic import ValidationError

from schema import Geography, Polity, Transition


def polity(polity_id: str, parent: str | None = None) -> Polity:
    return Polity.model_validate(
        {
            "id": polity_id,
            "canonical_name": polity_id,
            "parent": parent,
            "start": 1,
            "end": 2,
            "start_confidence": "low",
            "end_confidence": "low",
        }
    )


class BuildRelationshipValidationTests(unittest.TestCase):
    def test_acyclic_parents_pass(self) -> None:
        self.assertEqual(find_parent_cycles([polity("child", "parent"), polity("parent")]), [])

    def test_parent_cycle_is_reported_once(self) -> None:
        result = find_parent_cycles([polity("first", "second"), polity("second", "first")])
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


if __name__ == "__main__":
    unittest.main()
