import unittest

from pipeline.wd_to_yaml import allocate_ids, parse_year, slugify, to_document


class WikidataToYamlTests(unittest.TestCase):
    def test_parse_year_handles_wikidata_timestamps_and_bce(self) -> None:
        self.assertEqual(parse_year("+0044-01-01T00:00:00Z"), 44)
        self.assertEqual(parse_year("-0509-01-01T00:00:00Z"), -509)
        self.assertIsNone(parse_year(None))

    def test_slugify_is_schema_compatible(self) -> None:
        self.assertEqual(slugify("Royaume d'Haïti"), "royaume_d_haiti")
        self.assertEqual(slugify("3rd Dynasty"), "polity_3rd_dynasty")

    def test_collisions_are_stable_and_qid_suffixed(self) -> None:
        rows = [
            {"qid": "Q20", "label_en": "Roman Empire"},
            {"qid": "Q10", "label_en": "Roman Empire"},
        ]
        self.assertEqual(
            [item[1] for item in allocate_ids(rows)],
            ["roman_empire_q20", "roman_empire_q10"],
        )

    def test_document_is_a_valid_draft_shape(self) -> None:
        document = to_document(
            {
                "qid": "Q42",
                "label_en": "Example Empire",
                "label_fr": "Empire exemple",
                "aliases_en": "Example realm|Example realm|Realm",
                "inception": "-0500-01-01T00:00:00Z",
                "dissolution": "+0100-01-01T00:00:00Z",
            },
            "example_empire",
        )
        self.assertEqual(document["start"], -500)
        self.assertEqual(document["end"], 100)
        self.assertEqual(document["weight_by_era"], {-500: 5})
        self.assertEqual(document["external_ids"], {"wikidata": "Q42"})


if __name__ == "__main__":
    unittest.main()
