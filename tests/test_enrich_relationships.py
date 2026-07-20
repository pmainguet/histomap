import unittest

from pipeline.enrich_relationships import PolityDates, assess, intervals_overlap, succession_dates_compatible


class RelationshipEnrichmentTests(unittest.TestCase):
    def test_interval_overlap(self) -> None:
        self.assertTrue(intervals_overlap(PolityDates(100, 300), PolityDates(200, 400)))
        self.assertFalse(intervals_overlap(PolityDates(100, 200), PolityDates(200, 300)))

    def test_succession_date_tolerance(self) -> None:
        self.assertTrue(succession_dates_compatible(PolityDates(100, 200), PolityDates(200, 400)))
        self.assertTrue(succession_dates_compatible(PolityDates(100, 200), PolityDates(700, 800)))
        self.assertFalse(succession_dates_compatible(PolityDates(100, 200), PolityDates(701, 800)))
        self.assertFalse(succession_dates_compatible(PolityDates(100, None), PolityDates(200, 400)))

    def test_reciprocal_parent_is_automatic(self) -> None:
        links = [
            {"source": "Q1", "property": "P361", "target": "Q2"},
            {"source": "Q2", "property": "P527", "target": "Q1"},
        ]
        result = assess(links, {"Q1": PolityDates(100, 200), "Q2": PolityDates(50, 250)})
        self.assertEqual(result[0]["decision"], "auto")

    def test_one_sided_successor_requires_review(self) -> None:
        links = [{"source": "Q1", "property": "P156", "target": "Q2"}]
        result = assess(links, {"Q1": PolityDates(100, 200), "Q2": PolityDates(200, 300)})
        self.assertEqual(result[0]["decision"], "review")

    def test_same_name_entities_are_not_auto_linked(self) -> None:
        links = [
            {"source": "Q1", "property": "P361", "target": "Q2"},
            {"source": "Q2", "property": "P527", "target": "Q1"},
        ]
        result = assess(
            links,
            {"Q1": PolityDates(100, 200), "Q2": PolityDates(100, 200)},
            {"Q1": "Roman Republic", "Q2": "Roman Republic"},
        )
        self.assertEqual(result[0]["decision"], "review")


if __name__ == "__main__":
    unittest.main()
