import json
import tempfile
import unittest
from pathlib import Path

from pipeline.reconcile import load_review_decisions
from pipeline.review_cli import pending_records, review_priority, save_decision


class ReviewCliTests(unittest.TestCase):
    def test_decisions_are_replaced_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.jsonl"
            save_decision({"seshat_id": "one", "decision": "reject"}, path)
            save_decision(
                {"seshat_id": "one", "decision": "accept", "polity_id": "polity"}, path
            )
            decisions = load_review_decisions(path)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions["one"]["polity_id"], "polity")

    def test_pending_queue_excludes_reviewed_and_non_review_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review_path = root / "reviews.jsonl"
            decision_path = root / "decisions.jsonl"
            records = [
                {"seshat_id": "one", "decision": "review"},
                {"seshat_id": "two", "decision": "review"},
                {"seshat_id": "three", "decision": "auto"},
            ]
            review_path.write_text(
                "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
            )
            save_decision({"seshat_id": "one", "decision": "reject"}, decision_path)
            pending = pending_records(review_path, decision_path)
        self.assertEqual([record["seshat_id"] for record in pending], ["two"])

    def test_priority_favors_globally_visible_prominent_candidates(self) -> None:
        record = {
            "start_year": 100,
            "end_year": 500,
            "peak_population_log10": 7,
            "peak_area_km2_log10": 6,
            "peak_social_complexity": 8,
            "candidates": [
                {"polity_id": "major", "total_score": 80},
                {"polity_id": "runner", "total_score": 78},
            ]
        }
        metadata = {
            "major": {
                "prominence_score": 75,
                "visibility_tier": "global",
                "external_ids": {},
            }
        }
        high, components = review_priority(record, metadata)
        low, _ = review_priority(record, {})
        self.assertGreater(high, low)
        self.assertEqual(components["tier"], 100)


if __name__ == "__main__":
    unittest.main()
