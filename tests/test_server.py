import json
import tempfile
import unittest
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from server.app import create_app


class UnifiedServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "web").mkdir()
        (self.root / "reports").mkdir()
        (self.root / "polities").mkdir()
        for name in ("index.html", "review.html", "styles.css", "app.js", "review.js"):
            (self.root / "web" / name).write_text(name, encoding="utf-8")
        (self.root / "data.json").write_text("[]", encoding="utf-8")
        polity = {
            "id": "candidate",
            "canonical_name": "Candidate",
            "prominence_score": 70,
            "visibility_tier": "global",
            "external_ids": {"wikidata": "Q123"},
        }
        (self.root / "polities" / "candidate.yaml").write_text(
            yaml.safe_dump(polity), encoding="utf-8"
        )
        review = {
            "seshat_id": "S1",
            "seshat_name": "Source",
            "start_year": 100,
            "end_year": 200,
            "decision": "review",
            "candidates": [
                {
                    "polity_id": "candidate",
                    "canonical_name": "Candidate",
                    "total_score": 80,
                    "name_score": 85,
                    "date_score": 90,
                    "geography_score": 50,
                }
            ],
        }
        (self.root / "reports" / "seshat_reconciliation.jsonl").write_text(
            json.dumps(review) + "\n", encoding="utf-8"
        )
        (self.root / "reports" / "seshat_review_decisions.jsonl").write_text(
            "", encoding="utf-8"
        )
        self.client = TestClient(create_app(self.root))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_serves_timeline_review_and_data(self) -> None:
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/review").status_code, 200)
        self.assertEqual(self.client.get("/data.json").json(), [])

    def test_lists_and_accepts_a_valid_candidate(self) -> None:
        payload = self.client.get("/api/reviews").json()
        self.assertEqual(payload["total"], 1)
        self.assertIn("search=Source", payload["items"][0]["source_links"][0]["url"])
        self.assertEqual(
            payload["items"][0]["candidates"][0]["source_links"][0]["url"],
            "https://www.wikidata.org/wiki/Q123",
        )
        response = self.client.post(
            "/api/reviews/S1", json={"decision": "accept", "polity_id": "candidate"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/reviews").json()["total"], 0)

    def test_rejects_candidate_not_in_the_review(self) -> None:
        response = self.client.post(
            "/api/reviews/S1", json={"decision": "accept", "polity_id": "invented"}
        )
        self.assertEqual(response.status_code, 422)

    def test_rejects_unknown_pipeline_action(self) -> None:
        self.assertEqual(self.client.post("/api/actions/arbitrary-command").status_code, 404)


if __name__ == "__main__":
    unittest.main()
