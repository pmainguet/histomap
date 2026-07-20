import unittest

from build import find_parent_cycles
from schema import Polity


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


if __name__ == "__main__":
    unittest.main()
