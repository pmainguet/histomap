import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import yaml

from pipeline.wd_to_yaml import allocate_ids, convert, parse_year, slugify, to_document


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
        self.assertEqual(document["eligibility"], "review")

    def test_convert_suffixes_slug_occupied_by_another_qid(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            output = root / "polities"
            output.mkdir()
            (output / "example_empire.yaml").write_text(
                yaml.safe_dump({"external_ids": {"wikidata": "Q1"}}), encoding="utf-8"
            )
            parquet = root / "input.parquet"
            pd.DataFrame(
                [{"qid": "Q2", "label_en": "Example Empire", "inception": "+0100"}]
            ).to_parquet(parquet)

            written, preserved, rejected = convert(parquet, output)

            self.assertEqual((written, preserved, rejected), (1, 0, 0))
            self.assertTrue((output / "example_empire_q2.yaml").exists())

    def test_convert_rejects_bad_dates_and_continues(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            parquet = root / "input.parquet"
            pd.DataFrame(
                [
                    {"qid": "Q1", "label_en": "Bad", "inception": "not-a-date"},
                    {"qid": "Q2", "label_en": "Good", "inception": "+0100"},
                ]
            ).to_parquet(parquet)

            result = convert(parquet, root / "polities")

            self.assertEqual(result, (1, 0, 1))
            self.assertTrue((root / "polities" / "good.yaml").exists())

    def test_convert_skips_type_exclusions(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            parquet = root / "input.parquet"
            pd.DataFrame(
                [
                    {"qid": "Q1", "label_en": "City", "inception": "+0100"},
                    {"qid": "Q2", "label_en": "Country", "inception": "+0100"},
                ]
            ).to_parquet(parquet)
            report = root / "decisions.jsonl"
            report.write_text(
                '{"qid":"Q1","decision":"excluded"}\n'
                '{"qid":"Q2","decision":"accepted"}\n',
                encoding="utf-8",
            )

            result = convert(parquet, root / "polities", type_report=report)

            self.assertEqual(result, (1, 0, 1))
            self.assertFalse((root / "polities" / "city.yaml").exists())
            country = yaml.safe_load((root / "polities" / "country.yaml").read_text())
            self.assertEqual(country["eligibility"], "accepted")


if __name__ == "__main__":
    unittest.main()
