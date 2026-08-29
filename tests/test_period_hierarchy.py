import unittest

from pipeline.period_hierarchy import PeriodHierarchy


def build_hierarchy(polities: list[dict] | None = None) -> PeriodHierarchy:
    periods = [
        {"id": "macro_a", "tier": "macro_chapter", "start": 0, "broader_periods": []},
        {"id": "regional_a", "tier": "regional_era", "start": 100, "broader_periods": ["macro_a"]},
        {"id": "period_a", "tier": "period", "start": 200, "broader_periods": ["regional_a"]},
        {"id": "period_b", "tier": "period", "start": 300, "broader_periods": ["regional_a"]},
    ]
    links = [
        {"period_id": "period_a", "entity_id": "polity_1"},
        {"period_id": "period_a", "entity_id": "polity_2"},
        {"period_id": "period_b", "entity_id": "polity_3"},
        {"period_id": "regional_a", "entity_id": "polity_4"},
    ]
    return PeriodHierarchy(periods=periods, period_links=links, polities=polities or [])


class AncestorsTests(unittest.TestCase):
    def test_root_first_chain(self) -> None:
        hierarchy = build_hierarchy()
        self.assertEqual(hierarchy.ancestors("period_a"), ["macro_a", "regional_a"])

    def test_macro_chapter_has_no_ancestors(self) -> None:
        hierarchy = build_hierarchy()
        self.assertEqual(hierarchy.ancestors("macro_a"), [])

    def test_unknown_id_raises(self) -> None:
        hierarchy = build_hierarchy()
        with self.assertRaises(KeyError):
            hierarchy.ancestors("does_not_exist")

    def test_cycle_raises_instead_of_hanging(self) -> None:
        periods = [
            {"id": "loop_a", "tier": "period", "start": 0, "broader_periods": ["loop_b"]},
            {"id": "loop_b", "tier": "period", "start": 0, "broader_periods": ["loop_a"]},
        ]
        hierarchy = PeriodHierarchy(periods=periods, period_links=[], polities=[])
        with self.assertRaises(ValueError):
            hierarchy.ancestors("loop_a")


class ChildrenTests(unittest.TestCase):
    def test_direct_children_ordered_by_start(self) -> None:
        hierarchy = build_hierarchy()
        self.assertEqual(hierarchy.children("regional_a"), ["period_a", "period_b"])

    def test_leaf_has_no_children(self) -> None:
        hierarchy = build_hierarchy()
        self.assertEqual(hierarchy.children("period_a"), [])


class EntitiesUnderTests(unittest.TestCase):
    def test_leaf_period_returns_its_own_links(self) -> None:
        hierarchy = build_hierarchy()
        self.assertEqual(sorted(hierarchy.entities_under("period_a")), ["polity_1", "polity_2"])

    def test_ancestor_returns_transitive_deduplicated_links(self) -> None:
        hierarchy = build_hierarchy()
        self.assertEqual(
            sorted(hierarchy.entities_under("regional_a")),
            ["polity_1", "polity_2", "polity_3", "polity_4"],
        )

    def test_macro_chapter_returns_everything_under_it(self) -> None:
        hierarchy = build_hierarchy()
        self.assertEqual(
            sorted(hierarchy.entities_under("macro_a")),
            ["polity_1", "polity_2", "polity_3", "polity_4"],
        )


class TopEntitiesTests(unittest.TestCase):
    def test_ranks_by_prominence_score_descending(self) -> None:
        polities = [
            {"id": "polity_1", "prominence_score": 10},
            {"id": "polity_2", "prominence_score": 90},
            {"id": "polity_3", "prominence_score": 50},
            {"id": "polity_4", "prominence_score": 30},
        ]
        hierarchy = build_hierarchy(polities)
        self.assertEqual(
            hierarchy.top_entities("macro_a", limit=2),
            ["polity_2", "polity_3"],
        )

    def test_visibility_override_is_pinned_first(self) -> None:
        polities = [
            {"id": "polity_1", "prominence_score": 10, "visibility_override": "global"},
            {"id": "polity_2", "prominence_score": 90},
        ]
        hierarchy = build_hierarchy(polities)
        self.assertEqual(hierarchy.top_entities("macro_a", limit=1), ["polity_1"])


class MacroChaptersTests(unittest.TestCase):
    def test_orders_by_start(self) -> None:
        periods = [
            {"id": "macro_b", "tier": "macro_chapter", "start": 500, "broader_periods": []},
            {"id": "macro_a", "tier": "macro_chapter", "start": 0, "broader_periods": []},
        ]
        hierarchy = PeriodHierarchy(periods=periods, period_links=[], polities=[])
        self.assertEqual(hierarchy.macro_chapters(), ["macro_a", "macro_b"])


if __name__ == "__main__":
    unittest.main()
