import json
import tempfile
import unittest
from pathlib import Path

import yaml

from pipeline.apply_review_decisions import apply_review_decisions


class ApplyReviewDecisionsTests(unittest.TestCase):
    def test_applies_accepts_and_preserves_rejects_as_separate_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            polities = root / "polities"
            reports = root / "reports"
            polities.mkdir()
            reports.mkdir()
            (polities / "target.yaml").write_text(
                yaml.safe_dump({"id": "target", "canonical_name": "Target", "sources": ["wikidata"]}),
                encoding="utf-8",
            )
            records = [
                {"seshat_id": "S1", "seshat_name": "Matched", "start_year": 1, "end_year": 2},
                {"seshat_id": "S2", "seshat_name": "Separate", "start_year": 3, "end_year": 4},
            ]
            review_path = reports / "reviews.jsonl"
            review_path.write_text(
                "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
            )
            decisions_path = reports / "decisions.jsonl"
            decisions_path.write_text(
                json.dumps({"seshat_id": "S1", "decision": "accept", "polity_id": "target"})
                + "\n"
                + json.dumps({"seshat_id": "S2", "decision": "reject"})
                + "\n",
                encoding="utf-8",
            )
            drafts_path = reports / "separate.yaml"

            counts = apply_review_decisions(
                review_path, decisions_path, polities, drafts_path
            )

            target = yaml.safe_load((polities / "target.yaml").read_text(encoding="utf-8"))
            draft = next(yaml.safe_load_all(drafts_path.read_text(encoding="utf-8")))
            self.assertEqual(counts, {"accepted": 1, "rejected": 1, "unchanged": 0})
            self.assertEqual(target["external_ids"]["seshat"], ["S1"])
            self.assertIn("seshat", target["sources"])
            self.assertEqual(draft["external_ids"]["seshat"], ["S2"])


if __name__ == "__main__":
    unittest.main()
