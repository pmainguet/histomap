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
        (self.root / "sources").mkdir()
        (self.root / "sources" / "wikidata_country_metadata.json").write_text(
            json.dumps({"Q142": {"iso2": "FR", "label": "France", "continents": ["europe"]}}),
            encoding="utf-8",
        )
        for name in (
            "index.html", "review.html", "type_review.html", "period_review.html", "styles.css", "app.js", "review.js",
            "type_review.js", "period_review.js",
        ):
            (self.root / "web" / name).write_text(name, encoding="utf-8")
        (self.root / "data.json").write_text("[]", encoding="utf-8")
        (self.root / "transitions.json").write_text("[]", encoding="utf-8")
        (self.root / "periods.json").write_text("[]", encoding="utf-8")
        (self.root / "period_links.json").write_text("[]", encoding="utf-8")
        (self.root / "period_links.yaml").write_text("[]\n", encoding="utf-8")
        polity = {
            "id": "candidate",
            "canonical_name": "Candidate",
            "prominence_score": 70,
            "visibility_tier": "global",
            "external_ids": {"wikidata": "Q123"},
            "start": 90,
            "end": 210,
            "sources": ["wikidata"],
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
        (self.root / "reports" / "entity_type_review.jsonl").write_text(
            json.dumps(
                {
                    "id": "candidate",
                    "canonical_name": "Candidate",
                    "wikidata": "Q123",
                    "proposed_type": "polity",
                    "confidence": "low",
                    "source_qids": [],
                    "reason": "no mapped direct type",
                }
            ) + "\n",
            encoding="utf-8",
        )
        (self.root / "reports" / "period_role_review.jsonl").write_text(
            json.dumps(
                {
                    "id": "candidate",
                    "canonical_name": "Candidate",
                    "wikidata": "Q123",
                    "entity_type": "civilization",
                    "period_kinds": ["historical"],
                    "direct_type_qids": ["Q11514315", "Q8432"],
                    "dates": [90, 210],
                    "prominence_score": 70,
                    "reason": "mixed role",
                }
            ) + "\n",
            encoding="utf-8",
        )
        self.client = TestClient(create_app(self.root))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_serves_timeline_review_and_data(self) -> None:
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/review").status_code, 200)
        self.assertEqual(self.client.get("/type-review").status_code, 200)
        self.assertEqual(self.client.get("/data.json").json(), [])
        self.assertEqual(self.client.get("/transitions.json").json(), [])
        self.assertEqual(self.client.get("/periods.json").json(), [])
        self.assertEqual(self.client.get("/period_links.json").json(), [])

    def test_lists_and_accepts_a_valid_candidate(self) -> None:
        payload = self.client.get("/api/reviews").json()
        self.assertEqual(payload["total"], 1)
        self.assertIn("search=Source", payload["items"][0]["source_links"][0]["url"])
        self.assertEqual(
            payload["items"][0]["source_links"][-1],
            {
                "label": "Google search",
                "url": "https://www.google.com/search?q=Source",
            },
        )
        self.assertEqual(
            payload["items"][0]["candidates"][0]["source_links"][0]["url"],
            "https://www.wikidata.org/wiki/Q123",
        )
        self.assertEqual(
            payload["items"][0]["candidates"][0]["source_links"][1]["label"],
            "Wikipedia (English)",
        )
        comparison = payload["items"][0]["candidates"][0]["source_links"][-1]
        self.assertEqual(comparison["label"], "Google comparison")
        self.assertEqual(
            comparison["url"],
            "https://www.google.com/search?q=Candidate%20vs%20Source",
        )
        self.assertEqual(payload["items"][0]["candidates"][0]["canonical_start"], 90)
        self.assertEqual(payload["items"][0]["candidates"][0]["canonical_end"], 210)
        self.assertEqual(payload["items"][0]["candidates"][0]["canonical_sources"], ["wikidata"])
        response = self.client.post(
            "/api/reviews/S1", json={"decision": "accept", "polity_id": "candidate"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/reviews").json()["total"], 0)

    def test_rejects_unknown_histomap_entity(self) -> None:
        response = self.client.post(
            "/api/reviews/S1", json={"decision": "accept", "polity_id": "invented"}
        )
        self.assertEqual(response.status_code, 422)

    def test_saved_review_is_removed_from_the_cached_queue(self) -> None:
        response = self.client.post("/api/reviews/S1", json={"decision": "reject"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/reviews").json()["total"], 0)
        self.assertEqual(
            self.client.post("/api/reviews/S1", json={"decision": "reject"}).status_code,
            404,
        )

    def test_accepts_entity_found_outside_proposed_candidates(self) -> None:
        other = {
            "id": "other",
            "canonical_name": "Other Entity",
            "eligibility": "accepted",
            "start": 100,
            "end": 200,
        }
        (self.root / "polities" / "other.yaml").write_text(
            yaml.safe_dump(other), encoding="utf-8"
        )
        client = TestClient(create_app(self.root))
        response = client.post(
            "/api/reviews/S1", json={"decision": "accept", "polity_id": "other"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["polity_id"], "other")

    def test_rejects_unknown_pipeline_action(self) -> None:
        self.assertEqual(self.client.post("/api/actions/arbitrary-command").status_code, 404)

    def test_searches_all_polities_by_alias(self) -> None:
        polity_path = self.root / "polities" / "candidate.yaml"
        polity = yaml.safe_load(polity_path.read_text(encoding="utf-8"))
        polity["names"] = {"aliases_en": "Alternate Candidate | Other name"}
        polity_path.write_text(yaml.safe_dump(polity), encoding="utf-8")
        client = TestClient(create_app(self.root))
        response = client.get("/api/polities/search", params={"q": "Alternate Candidate"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["polity_id"], "candidate")
        self.assertEqual(response.json()["items"][0]["search_score"], 100)

    def test_lists_and_updates_geography_with_controlled_values(self) -> None:
        options = self.client.get("/api/options/geography").json()
        self.assertIn("europe", options["continents"])
        self.assertIn(
            {"code": "FR", "label": "France", "continents": ["europe"]},
            options["countries"],
        )
        response = self.client.patch(
            "/api/polities/candidate/geography",
            json={
                "continents": ["europe"],
                "primary_continent": "europe",
                "present_countries": ["FR"],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["geography"]["present_countries"], ["FR"])
        saved = yaml.safe_load(
            (self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(saved["geography"]["confidence"], "high")
        self.assertIn("geography", saved["manual_overrides"])

    def test_rejects_unknown_geography_values(self) -> None:
        response = self.client.patch(
            "/api/polities/candidate/geography",
            json={"continents": ["atlantis"], "present_countries": ["ZZ"]},
        )
        self.assertEqual(response.status_code, 422)

    def test_updates_and_locks_entity_type(self) -> None:
        response = self.client.patch(
            "/api/polities/candidate/entity-type", json={"entity_type": "culture"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["entity_type"], "culture")
        saved = yaml.safe_load(
            (self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(saved["entity_type_confidence"], "high")
        self.assertIn("entity_type", saved["manual_overrides"])

    def test_lists_and_saves_entity_type_review(self) -> None:
        payload = self.client.get("/api/type-reviews").json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["id"], "candidate")
        response = self.client.post(
            "/api/type-reviews/candidate", json={"entity_type": "civilization"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["entity_type"], "civilization")
        self.assertEqual(self.client.get("/api/type-reviews").json()["total"], 0)

    def test_lists_and_saves_period_role_as_linked_records(self) -> None:
        payload = self.client.get("/api/period-role-reviews").json()
        self.assertEqual(payload["total"], 1)
        response = self.client.post(
            "/api/period-role-reviews/candidate", json={"timeline_role": "both"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["period_id"], "candidate_period")
        entity = yaml.safe_load((self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8"))
        self.assertEqual(entity["timeline_role"], "both")
        self.assertIn("timeline_role", entity["manual_overrides"])
        self.assertTrue((self.root / "periods" / "candidate_period.yaml").exists())
        links = yaml.safe_load((self.root / "period_links.yaml").read_text(encoding="utf-8"))
        self.assertEqual(links[-1]["entity_id"], "candidate")
        self.assertEqual(self.client.get("/api/period-role-reviews").json()["total"], 0)


if __name__ == "__main__":
    unittest.main()
