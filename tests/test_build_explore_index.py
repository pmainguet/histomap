import unittest

from pipeline.build_explore_index import build_explore_index


def polity(id_: str, score: float, start: int = 0, end: int | None = 100) -> dict:
    return {
        "id": id_,
        "canonical_name": id_.replace("_", " ").title(),
        "start": start,
        "end": end,
        "prominence_score": score,
    }


class BuildExploreIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.periods = [
            {"id": "macro_a", "tier": "macro_chapter", "canonical_name": "Chapter A", "start": 0, "end": 1000, "broader_periods": []},
            {"id": "macro_b", "tier": "macro_chapter", "canonical_name": "Chapter B", "start": 1000, "end": 2000, "broader_periods": []},
            {"id": "period_a", "tier": "period", "canonical_name": "Period A", "start": 100, "end": 200, "broader_periods": ["macro_a"]},
        ]
        self.period_links = [
            {"period_id": "period_a", "entity_id": "polity_1"},
            {"period_id": "period_a", "entity_id": "polity_2"},
        ]
        self.polities = [polity("polity_1", 90), polity("polity_2", 10)]

    def test_one_entry_per_macro_chapter_ordered_by_start(self) -> None:
        result = build_explore_index(self.polities, self.periods, self.period_links)
        self.assertEqual([r["id"] for r in result], ["macro_a", "macro_b"])

    def test_entity_count_and_ranked_top_entities(self) -> None:
        result = build_explore_index(self.polities, self.periods, self.period_links, top_n=1)
        chapter_a = next(r for r in result if r["id"] == "macro_a")
        self.assertEqual(chapter_a["entity_count"], 2)
        self.assertEqual(len(chapter_a["top_entities"]), 1)
        self.assertEqual(chapter_a["top_entities"][0]["id"], "polity_1")  # higher prominence_score

    def test_chapter_with_no_linked_entities_still_included(self) -> None:
        result = build_explore_index(self.polities, self.periods, self.period_links)
        chapter_b = next(r for r in result if r["id"] == "macro_b")
        self.assertEqual(chapter_b["entity_count"], 0)
        self.assertEqual(chapter_b["top_entities"], [])


if __name__ == "__main__":
    unittest.main()
