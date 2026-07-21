import unittest

from pipeline.cache_wikidata_type_ancestors import effective_parent_qids


def claim(qid: str, rank: str) -> dict:
    return {
        "rank": rank,
        "mainsnak": {"datavalue": {"value": {"id": qid}}},
    }


class WikidataTypeAncestryTests(unittest.TestCase):
    def test_preferred_parent_replaces_normal_parent(self) -> None:
        self.assertEqual(
            effective_parent_qids([claim("Q_preferred", "preferred"), claim("Q_normal", "normal")]),
            ["Q_preferred"],
        )

    def test_deprecated_parent_is_ignored(self) -> None:
        self.assertEqual(
            effective_parent_qids([claim("Q_deprecated", "deprecated"), claim("Q_normal", "normal")]),
            ["Q_normal"],
        )


if __name__ == "__main__":
    unittest.main()
