import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import yaml

from pipeline.audit_civilizations import audit


class CivilizationAuditTests(unittest.TestCase):
    def test_reports_extraction_import_and_type_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            polities = root / "polities"
            polities.mkdir()
            (polities / "known.yaml").write_text(
                yaml.safe_dump(
                    {
                        "id": "known",
                        "external_ids": {"wikidata": "Q1"},
                        "entity_type": "civilization",
                        "eligibility": "accepted",
                    }
                ),
                encoding="utf-8",
            )
            parquet = root / "wikidata.parquet"
            pd.DataFrame(
                [
                    {"qid": "Q1", "inception": "-1000"},
                    {"qid": "Q2", "inception": None},
                    {"qid": "Q3", "inception": "-500"},
                ]
            ).to_parquet(parquet, index=False)
            rows = [
                {"qid": qid, "label": qid, "direct_type_qid": "Q8432", "direct_type_label": "civilization"}
                for qid in ("Q1", "Q2", "Q3", "Q4")
            ]
            report = root / "audit.jsonl"
            summary = root / "summary.md"

            counts = audit(
                rows,
                polities_dir=polities,
                parquet_path=parquet,
                report_path=report,
                summary_path=summary,
            )

            self.assertEqual(counts["canonical_civilization"], 1)
            self.assertEqual(counts["dateless_review"], 1)
            self.assertEqual(counts["awaiting_import"], 1)
            self.assertEqual(counts["missing_extraction"], 1)
            records = [json.loads(line) for line in report.read_text(encoding="utf-8").splitlines()]
            self.assertFalse(next(row for row in records if row["qid"] == "Q2")["has_inception"])


if __name__ == "__main__":
    unittest.main()
