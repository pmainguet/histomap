import json
import tempfile
import unittest
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from server.app import create_app, entity_type_review_sort_key


class UnifiedServerTests(unittest.TestCase):
    def test_type_reviews_group_civilizations_before_polities(self) -> None:
        reviews = [
            {"canonical_name": "Culture", "proposed_type": "culture", "confidence": "medium"},
            {"canonical_name": "Polity", "proposed_type": "polity", "confidence": "medium"},
            {"canonical_name": "Civilization", "proposed_type": "civilization", "confidence": "low"},
        ]

        ordered = sorted(reviews, key=entity_type_review_sort_key)

        self.assertEqual(
            [review["proposed_type"] for review in ordered],
            ["civilization", "polity", "culture"],
        )

    def test_accepts_micronation_entity_type(self) -> None:
        response = self.client.patch(
            "/api/polities/candidate/entity-type", json={"entity_type": "micronation"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["entity_type"], "micronation")

    def test_accepts_subdivision_entity_type(self) -> None:
        response = self.client.patch(
            "/api/polities/candidate/entity-type",
            json={"entity_type": "subdivision"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["entity_type"], "subdivision")
        saved = yaml.safe_load(
            (self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(saved["subdivision_parent_status"], "pending")
        queue = self.client.get("/api/subdivision-reviews").json()
        self.assertEqual(queue["items"][0]["id"], "candidate")
        self.assertEqual(queue["items"][0]["candidates"][0]["id"], "container")
        linked = self.client.post(
            "/api/subdivision-reviews/candidate", json={"parent_id": "container"}
        )
        self.assertEqual(linked.status_code, 200)
        saved = yaml.safe_load(
            (self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(saved["parent"], "container")
        self.assertEqual(saved["subdivision_parent_status"], "confirmed")

    def test_rejects_invalid_subdivision_parent(self) -> None:
        self.client.patch(
            "/api/polities/candidate/entity-type", json={"entity_type": "subdivision"}
        )
        response = self.client.post(
            "/api/subdivision-reviews/candidate", json={"parent_id": "missing"}
        )

        self.assertEqual(response.status_code, 422)

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
        (self.root / "sources" / "wikidata_relationships.json").write_text(
            json.dumps([{"source": "Q123", "property": "P17", "target": "Q999"}]),
            encoding="utf-8",
        )
        (self.root / "sources" / "wikidata_direct_types.json").write_text(
            json.dumps({"Q123": {"types": ["Q111", "Q222"]}}), encoding="utf-8"
        )
        for name in (
            "index.html", "review.html", "type_review.html", "period_review.html", "styles.css", "app.js", "review.js",
            "type_review.js", "subdivision_review.js", "period_review.js",
            "subdivision_review.html",
            "reviews.html", "reviews.js", "consolidation_review.html", "consolidation_review.js",
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
        (self.root / "polities" / "container.yaml").write_text(
            yaml.safe_dump(
                {
                    **polity,
                    "id": "container",
                    "canonical_name": "Container",
                    "external_ids": {"wikidata": "Q999"},
                    "entity_type": "polity",
                    "entity_type_confidence": "high",
                }
            ),
            encoding="utf-8",
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
        self.assertEqual(self.client.get("/subdivision-review").status_code, 200)
        self.assertEqual(self.client.get("/reviews").status_code, 200)
        self.assertEqual(self.client.get("/consolidation-review").status_code, 200)
        self.assertEqual(self.client.get("/data.json").json(), [])
        self.assertEqual(self.client.get("/transitions.json").json(), [])
        self.assertEqual(self.client.get("/periods.json").json(), [])
        self.assertEqual(self.client.get("/period_links.json").json(), [])

    def test_review_dashboard_lists_pipeline_counts(self) -> None:
        payload = self.client.get("/api/review-dashboard").json()["pipelines"]

        self.assertEqual(payload["entity_type"], 1)
        self.assertEqual(payload["source_matching"], 1)
        self.assertIn("consolidation", payload)
        self.assertIn("subdivision_parent", payload)
        self.assertIn("period_role", payload)

    def test_keeps_consolidation_candidate_independent(self) -> None:
        response = self.client.post(
            "/api/consolidation-reviews/candidate", json={"decision": "independent"}
        )

        self.assertEqual(response.status_code, 200)
        saved = yaml.safe_load((self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8"))
        self.assertEqual(saved["consolidation_status"], "independent")

    def test_converts_entity_phase_to_period_linked_to_target(self) -> None:
        response = self.client.post(
            "/api/consolidation-reviews/candidate",
            json={"decision": "phase_of", "target_id": "container"},
        )

        self.assertEqual(response.status_code, 200)
        saved = yaml.safe_load((self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8"))
        self.assertEqual(saved["timeline_role"], "retired")
        self.assertEqual(saved["consolidated_into"], "container")
        self.assertTrue((self.root / "periods" / "candidate_period.yaml").exists())
        links = yaml.safe_load((self.root / "period_links.yaml").read_text(encoding="utf-8"))
        self.assertTrue(any(link["period_id"] == "candidate_period" and link["entity_id"] == "container" for link in links))

    def test_merges_duplicate_identity_without_deleting_source(self) -> None:
        response = self.client.post(
            "/api/consolidation-reviews/candidate",
            json={"decision": "same_entity", "target_id": "container"},
        )

        self.assertEqual(response.status_code, 200)
        source = yaml.safe_load((self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8"))
        target = yaml.safe_load((self.root / "polities" / "container.yaml").read_text(encoding="utf-8"))
        self.assertEqual(source["consolidation_status"], "same_entity")
        self.assertIn("Candidate", target["names"]["aliases_en"])

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
        self.assertEqual(payload["items"][0]["direct_type_qids"], ["Q111", "Q222"])
        response = self.client.post(
            "/api/type-reviews/candidate", json={"entity_type": "civilization"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["entity_type"], "civilization")
        saved = yaml.safe_load(
            (self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8")
        )
        self.assertIn("polity", saved["entity_type_reviewed_against"])
        self.assertEqual(self.client.get("/api/type-reviews").json()["total"], 0)

    def test_saved_reconsideration_does_not_immediately_reappear(self) -> None:
        review_path = self.root / "reports" / "entity_type_review.jsonl"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review.update({"proposed_type": "subdivision", "reconsideration": True})
        review_path.write_text(json.dumps(review) + "\n", encoding="utf-8")
        client = TestClient(create_app(self.root))

        response = client.post(
            "/api/type-reviews/candidate", json={"entity_type": "subdivision"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.get("/api/type-reviews").json()["total"], 0)

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
