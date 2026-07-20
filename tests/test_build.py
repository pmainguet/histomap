import unittest

from build import find_parent_cycles
from pydantic import ValidationError

from schema import Geography, Polity


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


if __name__ == "__main__":
    unittest.main()
