import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pipeline.extract_maddison import detect_table, normalize


class MaddisonExtractionTests(unittest.TestCase):
    def test_normalizes_mpd_columns_and_population_units(self) -> None:
        frame = pd.DataFrame(
            {
                "countrycode": ["GBR", "GBR", "FRA"],
                "country": ["United Kingdom", "United Kingdom", "France"],
                "year": [1, 2, "not a year"],
                "gdppc": [1200.5, None, 900],
                "pop": [10.25, 11, 12],
            }
        )
        result = normalize(frame)
        self.assertEqual(len(result), 2)
        self.assertEqual(result["population"].tolist(), [10250, 11000])
        self.assertEqual(result["year"].tolist(), [1, 2])

    def test_detects_a_header_below_workbook_notes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "maddison.xlsx"
            rows = [
                ["Maddison Project Database", None, None, None, None],
                ["countrycode", "country", "year", "gdppc", "pop"],
                ["GBR", "United Kingdom", 1, 1200, 10],
            ]
            pd.DataFrame(rows).to_excel(path, sheet_name="Full data", header=False, index=False)
            self.assertEqual(detect_table(path), ("Full data", 1))

    def test_requires_both_measure_columns(self) -> None:
        frame = pd.DataFrame({"country": ["France"], "year": [1], "pop": [10]})
        with self.assertRaisesRegex(ValueError, "gdp_per_capita"):
            normalize(frame)


if __name__ == "__main__":
    unittest.main()
