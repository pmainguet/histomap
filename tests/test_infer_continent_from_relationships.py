"""Tests for pipeline/infer_continent_from_relationships.py -- inferring a
still-missing `continents` value from a documented Wikidata relationship
neighbor's own continents."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from pipeline.infer_continent_from_relationships import (
    apply_proposals,
    is_safe,
    neighbor_qids,
    propose_continents,
)


class InferContinentFromRelationshipsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "polities").mkdir()
        self.relationship_cache = self.root / "wikidata_relationships.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_polity(self, polity_id: str, qid: str | None, continents: list[str] | None = None,
                      manual_overrides: list | None = None) -> None:
        document: dict = {"id": polity_id, "canonical_name": polity_id}
        if qid:
            document["external_ids"] = {"wikidata": qid}
        geography: dict = {}
        if continents is not None:
            geography["continents"] = continents
        if geography:
            document["geography"] = geography
        if manual_overrides is not None:
            document["manual_overrides"] = manual_overrides
        (self.root / "polities" / f"{polity_id}.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
        )

    def write_relationships(self, links: list[dict]) -> None:
        self.relationship_cache.write_text(json.dumps(links), encoding="utf-8")

    def patched(self):
        return patch("pipeline.infer_continent_from_relationships.POLITIES_DIR", self.root / "polities"), patch(
            "pipeline.infer_continent_from_relationships.RELATIONSHIP_CACHE", self.relationship_cache
        )

    def test_neighbor_qids_both_directions(self) -> None:
        links = [
            {"source": "Q1", "property": "P361", "target": "Q2"},
            {"source": "Q3", "property": "P1366", "target": "Q1"},
            {"source": "Q1", "property": "P17", "target": "Q4"},  # not a relationship property
        ]
        self.assertEqual(neighbor_qids("Q1", links), {"Q2": {"P361"}, "Q3": {"P1366"}})

    def test_unambiguous_neighbor_continent_is_proposed(self) -> None:
        self.write_polity("gap_polity", "Q100")
        self.write_polity("known_neighbor", "Q200", continents=["asia"])
        self.write_relationships([{"source": "Q100", "property": "P361", "target": "Q200"}])
        p1, p2 = self.patched()
        with p1, p2:
            proposals = propose_continents()
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["id"], "gap_polity")
        self.assertEqual(proposals[0]["continent"], "asia")
        self.assertEqual(proposals[0]["neighbor_qids"], ["Q200"])
        self.assertTrue(proposals[0]["has_containment_evidence"])  # P361

    def test_single_succession_link_flagged_unsafe(self) -> None:
        self.write_polity("gap_polity", "Q100")
        self.write_polity("known_neighbor", "Q200", continents=["asia"])
        self.write_relationships([{"source": "Q100", "property": "P1365", "target": "Q200"}])
        p1, p2 = self.patched()
        with p1, p2:
            proposals = propose_continents()
        self.assertEqual(len(proposals), 1)
        self.assertFalse(proposals[0]["has_containment_evidence"])
        self.assertEqual(proposals[0]["neighbor_count"], 1)
        self.assertFalse(is_safe(proposals[0]))

    def test_two_agreeing_succession_neighbors_is_safe(self) -> None:
        self.write_polity("gap_polity", "Q100")
        self.write_polity("neighbor_a", "Q200", continents=["asia"])
        self.write_polity("neighbor_b", "Q300", continents=["asia"])
        self.write_relationships([
            {"source": "Q100", "property": "P1365", "target": "Q200"},
            {"source": "Q100", "property": "P1366", "target": "Q300"},
        ])
        p1, p2 = self.patched()
        with p1, p2:
            proposals = propose_continents()
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["neighbor_count"], 2)
        self.assertTrue(is_safe(proposals[0]))

    def test_disagreeing_neighbors_are_not_proposed(self) -> None:
        self.write_polity("gap_polity", "Q100")
        self.write_polity("neighbor_asia", "Q200", continents=["asia"])
        self.write_polity("neighbor_europe", "Q300", continents=["europe"])
        self.write_relationships([
            {"source": "Q100", "property": "P361", "target": "Q200"},
            {"source": "Q100", "property": "P527", "target": "Q300"},
        ])
        p1, p2 = self.patched()
        with p1, p2:
            proposals = propose_continents()
        self.assertEqual(proposals, [])

    def test_locked_geography_is_never_proposed(self) -> None:
        self.write_polity("gap_polity", "Q100", manual_overrides=["geography"])
        self.write_polity("known_neighbor", "Q200", continents=["asia"])
        self.write_relationships([{"source": "Q100", "property": "P361", "target": "Q200"}])
        p1, p2 = self.patched()
        with p1, p2:
            proposals = propose_continents()
        self.assertEqual(proposals, [])

    def test_already_has_continents_is_never_proposed(self) -> None:
        self.write_polity("has_continent", "Q100", continents=["africa"])
        self.write_polity("known_neighbor", "Q200", continents=["asia"])
        self.write_relationships([{"source": "Q100", "property": "P361", "target": "Q200"}])
        p1, p2 = self.patched()
        with p1, p2:
            proposals = propose_continents()
        self.assertEqual(proposals, [])

    def test_no_qid_is_never_proposed(self) -> None:
        self.write_polity("no_qid", None)
        self.write_relationships([])
        p1, p2 = self.patched()
        with p1, p2:
            proposals = propose_continents()
        self.assertEqual(proposals, [])

    def test_apply_proposals_writes_continents(self) -> None:
        self.write_polity("gap_polity", "Q100")
        with patch("pipeline.infer_continent_from_relationships.POLITIES_DIR", self.root / "polities"):
            applied = apply_proposals(
                [{"id": "gap_polity", "continent": "asia", "neighbor_qids": ["Q200"]}]
            )
        self.assertEqual(applied, 1)
        document = yaml.safe_load((self.root / "polities" / "gap_polity.yaml").read_text(encoding="utf-8"))
        self.assertEqual(document["geography"]["continents"], ["asia"])
        self.assertEqual(document["geography"]["confidence"], "low")

    def test_apply_proposals_skips_a_record_since_resolved_another_way(self) -> None:
        # A record could gain continents from a different pass between
        # propose_continents() being called and apply_proposals() actually
        # writing -- must not clobber it.
        self.write_polity("gap_polity", "Q100", continents=["europe"])
        with patch("pipeline.infer_continent_from_relationships.POLITIES_DIR", self.root / "polities"):
            applied = apply_proposals(
                [{"id": "gap_polity", "continent": "asia", "neighbor_qids": ["Q200"]}]
            )
        self.assertEqual(applied, 0)
        document = yaml.safe_load((self.root / "polities" / "gap_polity.yaml").read_text(encoding="utf-8"))
        self.assertEqual(document["geography"]["continents"], ["europe"])


if __name__ == "__main__":
    unittest.main()
