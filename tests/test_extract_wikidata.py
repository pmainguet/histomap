import unittest

from pipeline.extract_wikidata import flatten_row, merge_into


class ExtractWikidataTests(unittest.TestCase):
    def test_flatten_ignores_non_numeric_quantity_bindings(self) -> None:
        row = {
            "item": {"value": "http://www.wikidata.org/entity/Q42"},
            "area": {"value": "123.5"},
            "population": {"value": "http://www.wikidata.org/.well-known/genid/example"},
            "wikipedia_en": {"value": "https://en.wikipedia.org/wiki/Douglas_Adams"},
        }

        flattened = flatten_row(row, ["Q7275"])

        self.assertEqual(flattened["area_km2"], 123.5)
        self.assertIsNone(flattened["population"])
        self.assertEqual(flattened["wikipedia_en"], "https://en.wikipedia.org/wiki/Douglas_Adams")

    def test_merge_combines_class_membership(self) -> None:
        rows = {}
        merge_into(rows, {"qid": "Q42", "label_en": None, "wd_classes": ["Q7275"]})
        merge_into(rows, {"qid": "Q42", "label_en": "Example", "wd_classes": ["Q48349"]})

        self.assertEqual(rows["Q42"]["label_en"], "Example")
        self.assertEqual(rows["Q42"]["wd_classes"], ["Q48349", "Q7275"])


if __name__ == "__main__":
    unittest.main()
