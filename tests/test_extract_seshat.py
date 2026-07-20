import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from pipeline.extract_seshat import normalize_workbook, parse_historical_date


class SeshatDateParserTests(unittest.TestCase):
    def test_numeric_and_approximate_bce(self) -> None:
        self.assertEqual(parse_historical_date(-550).year, -550)
        parsed = parse_historical_date("c. 550 BCE")
        self.assertEqual((parsed.year, parsed.confidence), (-550, "medium"))

    def test_range_uses_requested_boundary(self) -> None:
        self.assertEqual(parse_historical_date("550-500 BCE", "start").year, -550)
        self.assertEqual(parse_historical_date("550-500 BCE", "end").year, -500)

    def test_qualified_century(self) -> None:
        self.assertEqual(parse_historical_date("early 4th century CE", "start").year, 300)
        self.assertEqual(parse_historical_date("early 4th century CE", "end").year, 332)
        self.assertEqual(parse_historical_date("late 4th century BCE", "start").year, -333)
        self.assertEqual(parse_historical_date("late 4th century BCE", "end").year, -300)


class SeshatWorkbookTests(unittest.TestCase):
    def test_normalizes_actual_equinox_sheet_shape(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "fixture.xlsx"
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                pd.DataFrame(
                    [
                        {
                            "NGA": "Test NGA",
                            "PolName": "Test Kingdom",
                            "LongName": "The Long Test Kingdom",
                            "PolID": "TsKing",
                            "Start": "c. 500 BCE",
                            "End": 100,
                            "World Region": "Test",
                            "Complexity": "Early",
                            "Dupl": "n",
                            "Language": "Testish",
                            "Genus": "Test",
                            "Family": "Test",
                        }
                    ]
                ).to_excel(writer, sheet_name="Polities", index=False)
                pd.DataFrame(
                    [{"NGA": "Test NGA", "PolID": "TsKing", "Time": 0, "Pop": 5.0, "Terr": 4.0}]
                ).to_excel(writer, sheet_name="AggrSCWarAgriRelig", index=False)
                pd.DataFrame(
                    [{"NGA": "Test NGA", "PolID": "TsKing", "Time": 0, "SPC": 6.5}]
                ).to_excel(writer, sheet_name="SPC_MilTech", index=False)

            polities, timeseries = normalize_workbook(path)

            self.assertEqual(len(polities), 1)
            self.assertEqual(polities.iloc[0]["start_year"], -500)
            self.assertEqual(polities.iloc[0]["start_confidence"], "medium")
            self.assertEqual(polities.iloc[0]["long_name"], "The Long Test Kingdom")
            self.assertEqual(polities.iloc[0]["ngas"], ["Test NGA"])
            self.assertEqual(timeseries.iloc[0]["social_complexity_index"], 6.5)


if __name__ == "__main__":
    unittest.main()
