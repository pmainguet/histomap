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
            "review_build.js", "events_review.html", "events_review.js",
        ):
            (self.root / "web" / name).write_text(name, encoding="utf-8")
        (self.root / "data.json").write_text("[]", encoding="utf-8")
        (self.root / "transitions.json").write_text("[]", encoding="utf-8")
        (self.root / "periods.json").write_text("[]", encoding="utf-8")
        (self.root / "period_links.json").write_text("[]", encoding="utf-8")
        (self.root / "period_links.yaml").write_text("[]\n", encoding="utf-8")
        (self.root / "events.json").write_text("[]", encoding="utf-8")
        polity = {
            "id": "candidate",
            "canonical_name": "Candidate",
            "prominence_score": 70,
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
        self.assertEqual(self.client.get("/events-review").status_code, 200)
        self.assertEqual(self.client.get("/data.json").json(), [])
        self.assertEqual(self.client.get("/transitions.json").json(), [])
        self.assertEqual(self.client.get("/periods.json").json(), [])
        self.assertEqual(self.client.get("/period_links.json").json(), [])
        self.assertEqual(self.client.get("/events.json").json(), [])

    def test_build_artifacts_force_browser_revalidation(self) -> None:
        # Found live, 7 September 2026: converting a polity to a period and
        # rebuilding correctly updated data.json/explore_tree.json on disk,
        # but /explore kept showing the stale pre-rebuild version -- these
        # routes carry only ETag/Last-Modified by default (FileResponse),
        # so browsers apply RFC 7234 heuristic freshness. Same class of bug
        # already fixed for /static/*, just never extended to these.
        for path in ("/data.json", "/transitions.json", "/periods.json", "/period_links.json", "/events.json"):
            self.assertEqual(self.client.get(path).headers.get("cache-control"), "no-cache")

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

    def test_review_dashboard_counts_pending_events(self) -> None:
        (self.root / "events").mkdir(exist_ok=True)
        (self.root / "events" / "pending_event.yaml").write_text(
            yaml.safe_dump({"id": "pending_event", "canonical_name": "Pending Event", "year": 210, "authority": "test"}),
            encoding="utf-8",
        )
        (self.root / "events" / "accepted_event.yaml").write_text(
            yaml.safe_dump({
                "id": "accepted_event", "canonical_name": "Accepted Event", "year": 210,
                "eligibility": "accepted", "authority": "test",
            }),
            encoding="utf-8",
        )
        client = TestClient(create_app(self.root))

        response = client.get("/api/review-dashboard").json()

        self.assertEqual(response["pipelines"]["events"], 1)

    def test_combined_identity_queue_handles_period_only_decision(self) -> None:
        queue = self.client.get("/api/consolidation-reviews").json()["items"]
        candidate = next(item for item in queue if item["id"] == "candidate")
        self.assertTrue(candidate["period_role_candidate"])
        # Live report, 7 September 2026: this candidate-less fallback entry
        # rendered with a generic "no compatible canonical target" message
        # that gave no hint it was actually a period-role decision -- the
        # queue payload always carried period_reason, but the frontend
        # never surfaced it. Locking in that the reason travels with the
        # item so the UI has something concrete to show instead.
        self.assertFalse(candidate["candidates"])
        self.assertEqual(candidate["period_reason"], "mixed role")

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

    def test_period_conversion_sets_promoted_from(self) -> None:
        self.client.post("/api/consolidation-reviews/candidate", json={"decision": "period"})
        period = yaml.safe_load(
            (self.root / "periods" / "candidate_period.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(period["promoted_from"], "candidate")

    def test_promote_period_to_entity_restores_the_original_polity_record(self) -> None:
        # The real, reachable "undo a promotion" path is /api/periods/{id}/
        # promote-to-entity, not decide_consolidation_review's "independent"
        # decision -- confirmed while writing this test: refresh_period_role_
        # queue() excludes any entity whose manual_overrides already contains
        # "timeline_role" (which save_timeline_role always sets on the FIRST
        # decision), so decide_consolidation_review's period_record-gated
        # revert branches can never fire a second time for an already-
        # promoted entity. See ROADMAP.md's note on this.
        self.client.post("/api/consolidation-reviews/candidate", json={"decision": "period"})
        self.assertTrue((self.root / "periods" / "candidate_period.yaml").exists())

        response = self.client.post(
            "/api/periods/candidate_period/promote-to-entity", json={"entity_type": "polity"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse((self.root / "periods" / "candidate_period.yaml").exists())
        saved = yaml.safe_load(
            (self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(saved["timeline_role"], "entity")
        # The original file (sources, prominence_score, etc.) is restored,
        # not synthesized fresh -- the polity file was never deleted by the
        # promotion in the first place.
        self.assertEqual(saved["prominence_score"], 70)
        self.assertEqual(saved["sources"], ["wikidata"])

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

    def test_keeps_consolidation_candidate_independent(self) -> None:
        response = self.client.post(
            "/api/consolidation-reviews/candidate", json={"decision": "independent"}
        )

        self.assertEqual(response.status_code, 200)
        saved = yaml.safe_load((self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8"))
        self.assertEqual(saved["consolidation_status"], "independent")

    def test_independent_decision_on_a_period_role_candidate_writes_no_timeline_role(self) -> None:
        # ROADMAP.md item 0, found 5 September 2026: decide_consolidation_
        # review used to call save_timeline_role(id, "entity", ...) here
        # whenever the entity was still in period_role_queue (true for
        # "candidate", seeded in setUp()) -- a redundant no-op write
        # (timeline_role was already "entity") that only ever fired before
        # any period-role decision had been made, since the *first*
        # promotion permanently drops the entity from that queue. Removed;
        # this locks in that "independent" only ever touches
        # consolidation_status, never timeline_role/manual_overrides.
        response = self.client.post(
            "/api/consolidation-reviews/candidate", json={"decision": "independent"}
        )

        self.assertEqual(response.status_code, 200)
        saved = yaml.safe_load((self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8"))
        self.assertNotIn("timeline_role", saved)
        self.assertNotIn("timeline_role", saved.get("manual_overrides", []))

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

    def test_creates_polity_with_minimum_fields(self) -> None:
        # ROADMAP.md item 0: minimal hand-authoring path, no Wikidata
        # ingestion or period conversion involved.
        response = self.client.post(
            "/api/polities",
            json={"canonical_name": "New Test Realm", "start": 1200, "end": 1300, "present_countries": ["FR"]},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["polity_id"], "new_test_realm")
        saved = yaml.safe_load((self.root / "polities" / "new_test_realm.yaml").read_text(encoding="utf-8"))
        self.assertEqual(saved["canonical_name"], "New Test Realm")
        self.assertEqual(saved["geography"]["present_countries"], ["FR"])
        self.assertEqual(saved["geography"]["continents"], ["europe"])
        self.assertEqual(saved["eligibility"], "accepted")
        # Immediately visible to other endpoints without a server restart --
        # metadata is refreshed in-process, same as every other write path.
        self.assertEqual(self.client.get("/api/polities/new_test_realm").status_code, 200)

    def test_create_polity_id_collision_gets_a_numeric_suffix(self) -> None:
        first = self.client.post(
            "/api/polities",
            json={"canonical_name": "Duplicate Name", "start": 1000, "present_countries": ["FR"]},
        ).json()
        second = self.client.post(
            "/api/polities",
            json={"canonical_name": "Duplicate Name", "start": 1500, "present_countries": ["FR"]},
        ).json()

        self.assertEqual(first["polity_id"], "duplicate_name")
        self.assertEqual(second["polity_id"], "duplicate_name_2")

    def test_create_polity_requires_present_countries(self) -> None:
        response = self.client.post(
            "/api/polities", json={"canonical_name": "No Geography Realm", "start": 1000}
        )

        self.assertEqual(response.status_code, 422)

    def test_create_polity_allows_open_ended_dates(self) -> None:
        response = self.client.post(
            "/api/polities",
            json={"canonical_name": "Still Extant Realm", "start": 1950, "present_countries": ["FR"]},
        )

        self.assertEqual(response.status_code, 200)
        saved = yaml.safe_load((self.root / "polities" / "still_extant_realm.yaml").read_text(encoding="utf-8"))
        self.assertIsNone(saved["end"])

    def test_creates_period_with_minimum_fields(self) -> None:
        response = self.client.post(
            "/api/periods",
            json={"canonical_name": "New Test Era", "start": -500, "end": 500, "present_countries": ["FR"]},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["period_id"], "new_test_era")
        saved = yaml.safe_load((self.root / "periods" / "new_test_era.yaml").read_text(encoding="utf-8"))
        self.assertEqual(saved["authority"], "Histomap editorial: manually created")
        self.assertEqual(saved["geography"]["present_countries"], ["FR"])
        self.assertEqual(saved["geography"]["continents"], ["europe"])

    def test_create_period_requires_a_finite_end(self) -> None:
        response = self.client.post(
            "/api/periods", json={"canonical_name": "Open Ended Era", "start": -500, "present_countries": ["FR"]}
        )

        self.assertEqual(response.status_code, 422)

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

    def test_searches_periods_by_name(self) -> None:
        # Backs the period detail_of picker (Task 5 of the periods-as-
        # details-of feature) -- a period's own detail_of target can be
        # another period, so it needs its own search endpoint, mirroring
        # /api/polities/search.
        period_path = self.root / "periods" / "jomon_period.yaml"
        period_path.write_text(
            yaml.safe_dump({
                "id": "jomon_period", "canonical_name": "Jomon period",
                "start": -10000, "end": -300, "authority": "test",
            }),
            encoding="utf-8",
        )
        client = TestClient(create_app(self.root))
        response = client.get("/api/periods/search", params={"q": "Jomon"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["period_id"], "jomon_period")

    def test_gets_one_politys_full_raw_fields(self) -> None:
        response = self.client.get("/api/polities/candidate")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "candidate")
        self.assertEqual(response.json()["canonical_name"], "Candidate")

    def test_get_polity_404s_for_unknown_id(self) -> None:
        response = self.client.get("/api/polities/does_not_exist")
        self.assertEqual(response.status_code, 404)

    def test_geography_options_exclude_defunct_states(self) -> None:
        # Found live, 7 September 2026: "Soviet Union" (a dissolved state,
        # not a valid answer to "which modern country is this territory in
        # today") showed up in the present-countries picker right next to
        # "Russia". country_metadata mirrors Wikidata's own country records,
        # which include defunct states with their own ISO codes -- excluded
        # here regardless of what the underlying cache contains. YU
        # (Yugoslavia) is deliberately NOT excluded -- see
        # historical_regions.py's own docstring for why it's a legitimate
        # code, unlike SU/CS/DD.
        (self.root / "sources" / "wikidata_country_metadata.json").write_text(
            json.dumps({
                "Q142": {"iso2": "FR", "label": "France", "continents": ["europe"]},
                "Q15180": {"iso2": "SU", "label": "Soviet Union", "continents": ["europe", "asia"]},
                "Q33946": {"iso2": "CS", "label": "Czechoslovakia", "continents": ["europe"]},
                "Q16957": {"iso2": "DD", "label": "German Democratic Republic", "continents": ["europe"]},
                "Q36704": {"iso2": "YU", "label": "Yugoslavia", "continents": ["europe"]},
            }),
            encoding="utf-8",
        )
        client = TestClient(create_app(self.root))

        options = client.get("/api/options/geography").json()

        codes = {country["code"] for country in options["countries"]}
        self.assertNotIn("SU", codes)
        self.assertNotIn("CS", codes)
        self.assertNotIn("DD", codes)
        self.assertIn("YU", codes)
        self.assertIn("FR", codes)

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

    def test_promotes_period_by_restoring_original_entity(self) -> None:
        period_path = self.root / "periods" / "candidate_period.yaml"
        period_path.write_text(
            yaml.safe_dump({
                "id": "candidate_period", "canonical_name": "Candidate",
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

    def test_promote_period_to_entity_as_subdivision_writes_no_dead_field(self) -> None:
        # ROADMAP.md item 0, found 5 September 2026: this endpoint used to
        # write subdivision_parent_status, a field the 4 September 2026
        # subdivision/parent merge removed from the schema entirely -- the
        # write was silently dead under extra="ignore". Removed; this locks
        # in its absence regardless of entity_type.
        self.client.post("/api/consolidation-reviews/candidate", json={"decision": "period"})

        response = self.client.post(
            "/api/periods/candidate_period/promote-to-entity", json={"entity_type": "subdivision"}
        )

        self.assertEqual(response.status_code, 200)
        saved = yaml.safe_load(
            (self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8")
        )
        self.assertNotIn("subdivision_parent_status", saved)

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
                "id": "existing_period", "canonical_name": "Existing",
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

    def test_deletes_a_polity_with_no_references(self) -> None:
        (self.root / "polities" / "lonely_polity.yaml").write_text(
            yaml.safe_dump({**{"id": "lonely_polity", "canonical_name": "Lonely Polity",
                                "start": 1000, "start_confidence": "low", "end_confidence": "low"}}),
            encoding="utf-8",
        )
        client = TestClient(create_app(self.root))

        response = client.delete("/api/polities/lonely_polity")

        self.assertEqual(response.status_code, 200)
        self.assertFalse((self.root / "polities" / "lonely_polity.yaml").exists())
        self.assertEqual(client.get("/api/polities/lonely_polity").status_code, 404)

    def test_delete_unknown_polity_returns_404(self) -> None:
        response = self.client.delete("/api/polities/no_such_polity")

        self.assertEqual(response.status_code, 404)

    def test_delete_polity_blocked_by_detail_of_reference(self) -> None:
        (self.root / "polities" / "detail_child.yaml").write_text(
            yaml.safe_dump({"id": "detail_child", "canonical_name": "Detail Child",
                             "start": 1000, "start_confidence": "low", "end_confidence": "low",
                             "detail_of": "candidate"}),
            encoding="utf-8",
        )
        client = TestClient(create_app(self.root))

        response = client.delete("/api/polities/candidate")

        self.assertEqual(response.status_code, 409)
        self.assertIn("detail_child", response.json()["detail"])
        self.assertTrue((self.root / "polities" / "candidate.yaml").exists())

    def test_delete_polity_blocked_by_successor_reference(self) -> None:
        (self.root / "polities" / "predecessor_polity.yaml").write_text(
            yaml.safe_dump({"id": "predecessor_polity", "canonical_name": "Predecessor",
                             "start": 900, "start_confidence": "low", "end_confidence": "low",
                             "successors": ["candidate"]}),
            encoding="utf-8",
        )
        client = TestClient(create_app(self.root))

        response = client.delete("/api/polities/candidate")

        self.assertEqual(response.status_code, 409)
        self.assertIn("predecessor_polity", response.json()["detail"])

    def test_delete_polity_blocked_by_relationship_reference(self) -> None:
        (self.root / "polities" / "related_polity.yaml").write_text(
            yaml.safe_dump({"id": "related_polity", "canonical_name": "Related",
                             "start": 900, "start_confidence": "low", "end_confidence": "low",
                             "relationships": [{"target": "candidate", "kind": "political_parent"}]}),
            encoding="utf-8",
        )
        client = TestClient(create_app(self.root))

        response = client.delete("/api/polities/candidate")

        self.assertEqual(response.status_code, 409)
        self.assertIn("related_polity", response.json()["detail"])

    def test_deletes_a_period_with_no_references(self) -> None:
        (self.root / "periods" / "lonely_period.yaml").write_text(
            yaml.safe_dump({"id": "lonely_period", "canonical_name": "Lonely Period",
                             "start": 1000, "end": 1100, "authority": "Editorial"}),
            encoding="utf-8",
        )

        response = self.client.delete("/api/periods/lonely_period")

        self.assertEqual(response.status_code, 200)
        self.assertFalse((self.root / "periods" / "lonely_period.yaml").exists())

    def test_delete_period_blocked_by_broader_periods_reference(self) -> None:
        (self.root / "periods" / "container_period.yaml").write_text(
            yaml.safe_dump({"id": "container_period", "canonical_name": "Container Period",
                             "start": 900, "end": 1200, "authority": "Editorial"}),
            encoding="utf-8",
        )
        (self.root / "periods" / "nested_period.yaml").write_text(
            yaml.safe_dump({"id": "nested_period", "canonical_name": "Nested Period",
                             "start": 1000, "end": 1100, "authority": "Editorial",
                             "broader_periods": ["container_period"]}),
            encoding="utf-8",
        )

        response = self.client.delete("/api/periods/container_period")

        self.assertEqual(response.status_code, 409)
        self.assertIn("nested_period", response.json()["detail"])
        self.assertTrue((self.root / "periods" / "container_period.yaml").exists())

    def test_delete_unknown_period_returns_404(self) -> None:
        response = self.client.delete("/api/periods/no_such_period")

        self.assertEqual(response.status_code, 404)

    def test_creates_event_with_minimum_fields(self) -> None:
        # ROADMAP.md item 5: hand-authored creation path, defaults to
        # eligibility: review so it lands in the review queue.
        response = self.client.post(
            "/api/events", json={"canonical_name": "Some New Event", "year": 1200},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["event_id"], "some_new_event")
        saved = yaml.safe_load((self.root / "events" / "some_new_event.yaml").read_text(encoding="utf-8"))
        self.assertEqual(saved["year"], 1200)
        self.assertEqual(saved["eligibility"], "review")

    def test_creates_event_with_detail_of_and_bounds(self) -> None:
        response = self.client.post(
            "/api/events",
            json={
                "canonical_name": "Attached Event", "year": 200,
                "detail_of": ["candidate"],
                "bounds": [{"target": "existing_period", "edge": "end"}],
            },
        )

        self.assertEqual(response.status_code, 200)
        saved = yaml.safe_load((self.root / "events" / "attached_event.yaml").read_text(encoding="utf-8"))
        self.assertEqual(saved["detail_of"], ["candidate"])
        self.assertEqual(saved["bounds"], [{"target": "existing_period", "edge": "end"}])

    def test_events_review_lists_review_events_with_resolved_targets(self) -> None:
        (self.root / "events").mkdir(exist_ok=True)
        (self.root / "events" / "pending_event.yaml").write_text(
            yaml.safe_dump({
                "id": "pending_event", "canonical_name": "Pending Event", "year": 210,
                "detail_of": ["candidate"], "authority": "test",
            }),
            encoding="utf-8",
        )
        client = TestClient(create_app(self.root))

        response = client.get("/api/events-review")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        item = next(i for i in body["items"] if i["id"] == "pending_event")
        self.assertEqual(item["detail_of_targets"], [{"id": "candidate", "canonical_name": "Candidate"}])

    def test_events_review_excludes_already_accepted_events(self) -> None:
        (self.root / "events").mkdir(exist_ok=True)
        (self.root / "events" / "accepted_event.yaml").write_text(
            yaml.safe_dump({
                "id": "accepted_event", "canonical_name": "Accepted Event", "year": 210,
                "eligibility": "accepted", "authority": "test",
            }),
            encoding="utf-8",
        )
        client = TestClient(create_app(self.root))

        response = client.get("/api/events-review")

        self.assertNotIn("accepted_event", [i["id"] for i in response.json()["items"]])

    def test_decide_event_review_accepts(self) -> None:
        (self.root / "events").mkdir(exist_ok=True)
        (self.root / "events" / "pending_event.yaml").write_text(
            yaml.safe_dump({"id": "pending_event", "canonical_name": "Pending Event", "year": 210, "authority": "test"}),
            encoding="utf-8",
        )
        client = TestClient(create_app(self.root))

        response = client.post("/api/events-review/pending_event", json={"decision": "accepted"})

        self.assertEqual(response.status_code, 200)
        saved = yaml.safe_load((self.root / "events" / "pending_event.yaml").read_text(encoding="utf-8"))
        self.assertEqual(saved["eligibility"], "accepted")

    def test_decide_event_review_rejects_keeps_audit_record(self) -> None:
        (self.root / "events").mkdir(exist_ok=True)
        (self.root / "events" / "pending_event.yaml").write_text(
            yaml.safe_dump({"id": "pending_event", "canonical_name": "Pending Event", "year": 210, "authority": "test"}),
            encoding="utf-8",
        )
        client = TestClient(create_app(self.root))

        response = client.post("/api/events-review/pending_event", json={"decision": "excluded"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue((self.root / "events" / "pending_event.yaml").exists())
        saved = yaml.safe_load((self.root / "events" / "pending_event.yaml").read_text(encoding="utf-8"))
        self.assertEqual(saved["eligibility"], "excluded")

    def test_updates_event_fields(self) -> None:
        (self.root / "events").mkdir(exist_ok=True)
        (self.root / "events" / "some_event.yaml").write_text(
            yaml.safe_dump({"id": "some_event", "canonical_name": "Some Event", "year": 210, "authority": "test"}),
            encoding="utf-8",
        )
        client = TestClient(create_app(self.root))

        response = client.patch("/api/events/some_event/fields", json={"year": 215})

        self.assertEqual(response.status_code, 200)
        saved = yaml.safe_load((self.root / "events" / "some_event.yaml").read_text(encoding="utf-8"))
        self.assertEqual(saved["year"], 215)

    def test_deletes_an_event(self) -> None:
        (self.root / "events").mkdir(exist_ok=True)
        (self.root / "events" / "some_event.yaml").write_text(
            yaml.safe_dump({"id": "some_event", "canonical_name": "Some Event", "year": 210, "authority": "test"}),
            encoding="utf-8",
        )
        client = TestClient(create_app(self.root))

        response = client.delete("/api/events/some_event")

        self.assertEqual(response.status_code, 200)
        self.assertFalse((self.root / "events" / "some_event.yaml").exists())

    def test_delete_unknown_event_returns_404(self) -> None:
        response = self.client.delete("/api/events/no_such_event")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
