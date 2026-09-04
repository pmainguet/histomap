import json
import tempfile
import unittest
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from server.app import create_app


class UnifiedServerTests(unittest.TestCase):
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
        self.assertNotIn("subdivision_parent_status", saved)
        self.assertNotIn("parent", saved)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "web").mkdir()
        (self.root / "reports").mkdir()
        (self.root / "polities").mkdir()
        (self.root / "periods").mkdir()
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
            "explore.html", "explore.js", "explore_timeline.js", "explore_details.js",
            "geological_epochs.js", "timeline_scale.js", "lane_packing.js", "common.js",
            "styles.css",
            "reviews.html", "reviews.js", "consolidation_review.html", "consolidation_review.js",
            "review_build.js",
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
            "start_confidence": "low",
            "end_confidence": "low",
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

    def test_root_redirects_to_explore(self) -> None:
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "/explore")

    def test_serves_explore_review_and_data(self) -> None:
        self.assertEqual(self.client.get("/explore").status_code, 200)
        self.assertEqual(self.client.get("/review").status_code, 404)
        self.assertEqual(self.client.get("/type-review").status_code, 404)
        self.assertEqual(self.client.get("/subdivision-review").status_code, 404)
        self.assertEqual(self.client.get("/reviews").status_code, 200)
        self.assertEqual(self.client.get("/consolidation-review").status_code, 200)
        self.assertEqual(self.client.get("/data.json").json(), [])
        self.assertEqual(self.client.get("/transitions.json").json(), [])
        self.assertEqual(self.client.get("/periods.json").json(), [])
        self.assertEqual(self.client.get("/period_links.json").json(), [])

    def test_review_dashboard_lists_pipeline_counts(self) -> None:
        response = self.client.get("/api/review-dashboard").json()
        payload = response["pipelines"]

        self.assertNotIn("entity_type", payload)
        self.assertNotIn("source_matching", payload)
        self.assertIn("consolidation", payload)
        self.assertNotIn("subdivision_parent", payload)
        self.assertNotIn("period_role", payload)
        self.assertIn("consolidation", response["breakdowns"])
        self.assertEqual(response["breakdowns"]["consolidation"]["period_role"], 1)

    def test_combined_identity_queue_handles_period_only_decision(self) -> None:
        queue = self.client.get("/api/consolidation-reviews").json()["items"]
        candidate = next(item for item in queue if item["id"] == "candidate")
        self.assertTrue(candidate["period_role_candidate"])

        response = self.client.post(
            "/api/consolidation-reviews/candidate", json={"decision": "period"}
        )

        self.assertEqual(response.status_code, 200)
        saved = yaml.safe_load((self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8"))
        self.assertEqual(saved["timeline_role"], "period")
        self.assertTrue((self.root / "periods" / "candidate_period.yaml").exists())

    def test_combined_identity_queue_allows_broad_period_without_old_period_flag(self) -> None:
        response = self.client.post(
            "/api/consolidation-reviews/container", json={"decision": "period"}
        )

        self.assertEqual(response.status_code, 200)
        saved = yaml.safe_load((self.root / "polities" / "container.yaml").read_text(encoding="utf-8"))
        self.assertEqual(saved["timeline_role"], "period")
        self.assertTrue((self.root / "periods" / "container_period.yaml").exists())

    def test_consolidation_uses_identity_evidence_not_alias_token_noise(self) -> None:
        base = {
            "entity_type": "polity", "entity_type_confidence": "high",
            "start_confidence": "low", "end_confidence": "low",
            "sources": ["wikidata"], "eligibility": "accepted",
        }
        documents = [
            {**base, "id": "rhodes_old", "canonical_name": "Rhodes", "names": {"aliases_en": "Ancient Rhodes"}, "start": -407, "end": 500, "prominence_score": 20, "geography": {"present_countries": ["GR"]}},
            {**base, "id": "rhodes_main", "canonical_name": "Rhodes", "names": {"aliases_en": "Rhodos"}, "start": -1600, "end": None, "prominence_score": 30, "geography": {"present_countries": ["GR"]}},
            {**base, "id": "appenzell", "canonical_name": "Canton of Appenzell Ausserrhoden", "names": {"aliases_en": "Appenzell Outer Rhodes"}, "start": 1513, "end": None, "prominence_score": 25, "geography": {"present_countries": ["CH"]}},
            {**base, "id": "ottoman_caliphate", "canonical_name": "Ottoman Caliphate", "start": 1517, "end": 1924, "prominence_score": 20, "geography": {"present_countries": ["TR"]}},
            {**base, "id": "ottoman_empire", "canonical_name": "Ottoman Empire", "start": 1299, "end": 1922, "prominence_score": 40, "geography": {"present_countries": ["TR"]}},
        ]
        for document in documents:
            (self.root / "polities" / f"{document['id']}.yaml").write_text(
                yaml.safe_dump(document), encoding="utf-8"
            )
        client = TestClient(create_app(self.root))
        queue = client.get("/api/consolidation-reviews", params={"limit": 100}).json()["items"]

        rhodes = next(item for item in queue if item["id"] == "rhodes_old")
        self.assertIn("rhodes_main", [item["id"] for item in rhodes["candidates"]])
        self.assertNotIn("appenzell", [item["id"] for item in rhodes["candidates"]])
        ottoman = next(item for item in queue if item["id"] == "ottoman_caliphate")
        self.assertIn("ottoman_empire", [item["id"] for item in ottoman["candidates"]])

    def test_keeps_consolidation_candidate_independent(self) -> None:
        response = self.client.post(
            "/api/consolidation-reviews/candidate", json={"decision": "independent"}
        )

        self.assertEqual(response.status_code, 200)
        saved = yaml.safe_load((self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8"))
        self.assertEqual(saved["consolidation_status"], "independent")

    def test_discards_out_of_scope_entity_without_deleting_audit_record(self) -> None:
        response = self.client.post(
            "/api/consolidation-reviews/candidate", json={"decision": "discarded"}
        )

        self.assertEqual(response.status_code, 200)
        saved = yaml.safe_load((self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8"))
        self.assertEqual(saved["eligibility"], "excluded")
        self.assertEqual(saved["timeline_role"], "retired")
        self.assertEqual(saved["consolidation_status"], "discarded")
        self.assertFalse(any(item["id"] == "candidate" for item in self.client.get("/api/consolidation-reviews").json()["items"]))

    def test_marks_entity_as_detail_of_target_without_creating_a_period(self) -> None:
        response = self.client.post(
            "/api/consolidation-reviews/candidate",
            json={"decision": "detail_of", "target_id": "container"},
        )

        self.assertEqual(response.status_code, 200)
        saved = yaml.safe_load((self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8"))
        self.assertNotEqual(saved.get("timeline_role", "entity"), "retired")
        self.assertEqual(saved["detail_of"], "container")
        self.assertNotIn("consolidation_status", saved)
        self.assertFalse((self.root / "periods" / "candidate_period.yaml").exists())

    def test_candidate_detail_of_marks_the_candidate_not_the_reviewed_entity(self) -> None:
        response = self.client.post(
            "/api/consolidation-reviews/candidate",
            json={"decision": "candidate_detail_of", "target_id": "container"},
        )

        self.assertEqual(response.status_code, 200)
        candidate_saved = yaml.safe_load((self.root / "polities" / "container.yaml").read_text(encoding="utf-8"))
        self.assertEqual(candidate_saved["detail_of"], "candidate")
        reviewed_saved = yaml.safe_load((self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8"))
        self.assertEqual(reviewed_saved["consolidation_status"], "independent")

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

    def test_gets_one_politys_full_raw_fields(self) -> None:
        response = self.client.get("/api/polities/candidate")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "candidate")
        self.assertEqual(response.json()["canonical_name"], "Candidate")

    def test_get_polity_404s_for_unknown_id(self) -> None:
        response = self.client.get("/api/polities/does_not_exist")
        self.assertEqual(response.status_code, 404)

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

    def test_geography_update_preserves_historical_regions(self) -> None:
        # historical_regions/primary_historical_region aren't part of this
        # form (continents/countries are the only controls) -- a save used to
        # silently drop them (found via norwegian_jarldom_of_orkney.yaml).
        first = self.client.patch(
            "/api/polities/candidate/geography",
            json={"continents": ["europe"], "primary_continent": "europe", "present_countries": ["FR"]},
        )
        self.assertEqual(first.status_code, 200)
        path = self.root / "polities" / "candidate.yaml"
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["geography"]["historical_regions"] = ["western_europe"]
        document["geography"]["primary_historical_region"] = "western_europe"
        path.write_text(yaml.safe_dump(document), encoding="utf-8")
        client = TestClient(create_app(self.root))

        second = client.patch(
            "/api/polities/candidate/geography",
            json={"continents": ["europe"], "primary_continent": "europe", "present_countries": ["FR"]},
        )

        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["geography"]["historical_regions"], ["western_europe"])
        saved = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["geography"]["historical_regions"], ["western_europe"])
        self.assertEqual(saved["geography"]["primary_historical_region"], "western_europe")

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

    def test_updates_and_locks_period_kind(self) -> None:
        period_path = self.root / "periods" / "test_period.yaml"
        period_path.write_text(
            yaml.safe_dump({"id": "test_period", "canonical_name": "Test", "kind": "historical"}),
            encoding="utf-8",
        )

        response = self.client.patch(
            "/api/periods/test_period/kind", json={"kind": "archaeological"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["kind"], "archaeological")
        saved = yaml.safe_load(period_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["kind"], "archaeological")
        self.assertIn("kind", saved["manual_overrides"])

    def test_rejects_unknown_period_kind_update(self) -> None:
        response = self.client.patch(
            "/api/periods/missing/kind", json={"kind": "historical"}
        )

        self.assertEqual(response.status_code, 404)

    def test_promotes_period_by_restoring_original_entity(self) -> None:
        period_path = self.root / "periods" / "candidate_period.yaml"
        period_path.write_text(
            yaml.safe_dump({
                "id": "candidate_period", "canonical_name": "Candidate", "kind": "historical",
                "start": 90, "end": 210, "authority": "Editorial", "source_urls": ["https://example.test"],
            }),
            encoding="utf-8",
        )
        entity_path = self.root / "polities" / "candidate.yaml"
        entity = yaml.safe_load(entity_path.read_text(encoding="utf-8"))
        entity.update({"timeline_role": "retired", "consolidation_status": "phase_of", "consolidated_into": "container"})
        entity_path.write_text(yaml.safe_dump(entity), encoding="utf-8")
        (self.root / "period_links.yaml").write_text(
            yaml.safe_dump([{"period_id": "candidate_period", "entity_id": "container"}]), encoding="utf-8"
        )

        response = self.client.post(
            "/api/periods/candidate_period/promote-to-entity", json={"entity_type": "civilization"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["entity_id"], "candidate")
        saved = yaml.safe_load(entity_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["timeline_role"], "entity")
        self.assertEqual(saved["entity_type"], "civilization")
        self.assertNotIn("consolidation_status", saved)
        self.assertNotIn("consolidated_into", saved)
        self.assertFalse(period_path.exists())
        self.assertEqual(yaml.safe_load((self.root / "period_links.yaml").read_text(encoding="utf-8")), [])

    def test_convert_to_period_creates_linked_period_when_keeping_entity(self) -> None:
        # /period-review (and its dedicated /api/period-role-reviews queue
        # endpoints) was retired -- this timeline_role: "both" capability
        # (period_links.yaml-linked period *and* the polity stays visible)
        # is now reached directly via convert-to-period's keep_entity flag,
        # not through a review queue. See STATUS.md.
        response = self.client.post(
            "/api/polities/candidate/convert-to-period", params={"keep_entity": "true"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["period_id"], "candidate_period")
        entity = yaml.safe_load((self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8"))
        self.assertEqual(entity["timeline_role"], "both")
        self.assertIn("timeline_role", entity["manual_overrides"])
        self.assertTrue((self.root / "periods" / "candidate_period.yaml").exists())
        links = yaml.safe_load((self.root / "period_links.yaml").read_text(encoding="utf-8"))
        self.assertEqual(links[-1]["entity_id"], "candidate")

    def test_convert_to_period_defaults_to_demoting_without_a_link(self) -> None:
        response = self.client.post("/api/polities/candidate/convert-to-period")
        self.assertEqual(response.status_code, 200)
        entity = yaml.safe_load((self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8"))
        self.assertEqual(entity["timeline_role"], "period")
        self.assertTrue((self.root / "periods" / "candidate_period.yaml").exists())
        links = yaml.safe_load((self.root / "period_links.yaml").read_text(encoding="utf-8"))
        self.assertEqual(links, [])

    def test_update_polity_fields_edits_arbitrary_fields_without_bloating_overrides(self) -> None:
        response = self.client.patch(
            "/api/polities/candidate/fields", json={"notes": "edited via panel"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["changed"], ["notes"])
        entity = yaml.safe_load((self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8"))
        self.assertEqual(entity["notes"], "edited via panel")
        self.assertEqual(entity["manual_overrides"], ["notes"])

    def test_update_polity_fields_rejects_invalid_entity_type(self) -> None:
        response = self.client.patch(
            "/api/polities/candidate/fields", json={"entity_type": "not_a_real_type"}
        )
        self.assertEqual(response.status_code, 422)

    def test_update_polity_fields_cannot_change_id(self) -> None:
        response = self.client.patch(
            "/api/polities/candidate/fields", json={"id": "hijacked"}
        )
        self.assertEqual(response.status_code, 200)
        entity = yaml.safe_load((self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8"))
        self.assertEqual(entity["id"], "candidate")

    def test_update_period_fields_can_set_tier_and_broader_periods(self) -> None:
        period_path = self.root / "periods" / "existing_period.yaml"
        period_path.write_text(
            yaml.safe_dump({
                "id": "existing_period", "canonical_name": "Existing", "kind": "historical",
                "start": 90, "end": 210, "authority": "Editorial", "source_urls": ["https://example.test"],
            }),
            encoding="utf-8",
        )

        response = self.client.patch(
            "/api/periods/existing_period/fields",
            json={"tier": "regional_era", "broader_periods": ["macro_chapter_stub"]},
        )

        self.assertEqual(response.status_code, 200)
        document = yaml.safe_load(period_path.read_text(encoding="utf-8"))
        self.assertEqual(document["tier"], "regional_era")
        self.assertEqual(document["broader_periods"], ["macro_chapter_stub"])


if __name__ == "__main__":
    unittest.main()
