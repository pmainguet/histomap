"""Tests for pipeline/enrich_geography_from_seshat.py -- filling a missing
`continents` value from Seshat's own `world_region` field."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import yaml

from pipeline.enrich_geography_from_seshat import run


class EnrichGeographyFromSeshatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "polities").mkdir()
        self.seshat_polities_path = self.root / "seshat_polities.parquet"
        self.seshat_crosswalk_path = self.root / "seshat_crosswalk.parquet"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_polity(self, polity_id: str, external_ids: dict | None = None,
                      manual_overrides: list | None = None) -> None:
        document: dict = {"id": polity_id, "canonical_name": polity_id}
        if external_ids is not None:
            document["external_ids"] = external_ids
        if manual_overrides is not None:
            document["manual_overrides"] = manual_overrides
        (self.root / "polities" / f"{polity_id}.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
        )

    def write_seshat_polities(self, rows: list[dict]) -> None:
        pd.DataFrame(rows, columns=["seshat_id", "world_region"]).to_parquet(self.seshat_polities_path)

    def write_crosswalk(self, rows: list[dict]) -> None:
        pd.DataFrame(rows, columns=["seshat_id", "polity_id"]).to_parquet(self.seshat_crosswalk_path)

    def patched(self):
        return (
            patch("pipeline.enrich_geography_from_seshat.POLITIES_DIR", self.root / "polities"),
            patch("pipeline.enrich_geography_from_seshat.SESHAT_POLITIES_PATH", self.seshat_polities_path),
            patch("pipeline.enrich_geography_from_seshat.SESHAT_CROSSWALK_PATH", self.seshat_crosswalk_path),
        )

    def test_direct_external_id_match_fills_continent(self) -> None:
        self.write_polity("badarian", external_ids={"seshat": "EgBadar"})
        self.write_seshat_polities([{"seshat_id": "EgBadar", "world_region": "Africa"}])
        self.write_crosswalk([])
        p1, p2, p3 = self.patched()
        with p1, p2, p3:
            filled = run()
        self.assertEqual(filled, 1)
        document = yaml.safe_load((self.root / "polities" / "badarian.yaml").read_text(encoding="utf-8"))
        self.assertEqual(document["geography"]["continents"], ["africa"])
        self.assertEqual(document["geography"]["confidence"], "low")

    def test_central_eurasia_maps_to_asia(self) -> None:
        self.write_polity("kushan_empire", external_ids={"seshat": "AfKushn"})
        self.write_seshat_polities([{"seshat_id": "AfKushn", "world_region": "CentralEurasia"}])
        self.write_crosswalk([])
        p1, p2, p3 = self.patched()
        with p1, p2, p3:
            run()
        document = yaml.safe_load((self.root / "polities" / "kushan_empire.yaml").read_text(encoding="utf-8"))
        self.assertEqual(document["geography"]["continents"], ["asia"])

    def test_crosswalk_fallback_when_no_own_external_id(self) -> None:
        self.write_polity("some_polity")  # no external_ids at all
        self.write_seshat_polities([{"seshat_id": "KhAngkL", "world_region": "SoutheastAsia"}])
        self.write_crosswalk([{"seshat_id": "KhAngkL", "polity_id": "some_polity"}])
        p1, p2, p3 = self.patched()
        with p1, p2, p3:
            filled = run()
        self.assertEqual(filled, 1)
        document = yaml.safe_load((self.root / "polities" / "some_polity.yaml").read_text(encoding="utf-8"))
        self.assertEqual(document["geography"]["continents"], ["asia"])

    def test_own_external_id_takes_precedence_over_crosswalk(self) -> None:
        # If a record has BOTH its own external_ids.seshat AND a crosswalk
        # entry, only the direct id is consulted -- avoids double-counting
        # or an inconsistent crosswalk overriding an asserted id.
        self.write_polity("some_polity", external_ids={"seshat": "EgBadar"})
        self.write_seshat_polities([
            {"seshat_id": "EgBadar", "world_region": "Africa"},
            {"seshat_id": "KhAngkL", "world_region": "SoutheastAsia"},
        ])
        self.write_crosswalk([{"seshat_id": "KhAngkL", "polity_id": "some_polity"}])
        p1, p2, p3 = self.patched()
        with p1, p2, p3:
            run()
        document = yaml.safe_load((self.root / "polities" / "some_polity.yaml").read_text(encoding="utf-8"))
        self.assertEqual(document["geography"]["continents"], ["africa"])

    def test_multiple_seshat_ids_disagreeing_on_continent_is_skipped(self) -> None:
        self.write_polity("merged_polity", external_ids={"seshat": ["EgBadar", "KhAngkL"]})
        self.write_seshat_polities([
            {"seshat_id": "EgBadar", "world_region": "Africa"},
            {"seshat_id": "KhAngkL", "world_region": "SoutheastAsia"},
        ])
        self.write_crosswalk([])
        p1, p2, p3 = self.patched()
        with p1, p2, p3:
            filled = run()
        self.assertEqual(filled, 0)

    def test_already_has_continents_is_untouched(self) -> None:
        self.write_polity("already_resolved", external_ids={"seshat": "EgBadar"})
        (self.root / "polities" / "already_resolved.yaml").write_text(
            yaml.safe_dump({
                "id": "already_resolved", "external_ids": {"seshat": "EgBadar"},
                "geography": {"continents": ["europe"]},
            }),
            encoding="utf-8",
        )
        self.write_seshat_polities([{"seshat_id": "EgBadar", "world_region": "Africa"}])
        self.write_crosswalk([])
        p1, p2, p3 = self.patched()
        with p1, p2, p3:
            filled = run()
        self.assertEqual(filled, 0)

    def test_locked_geography_is_left_alone(self) -> None:
        self.write_polity(
            "locked_polity", external_ids={"seshat": "EgBadar"}, manual_overrides=["geography"],
        )
        self.write_seshat_polities([{"seshat_id": "EgBadar", "world_region": "Africa"}])
        self.write_crosswalk([])
        p1, p2, p3 = self.patched()
        with p1, p2, p3:
            filled = run()
        self.assertEqual(filled, 0)

    def test_no_crosswalk_file_is_handled_gracefully(self) -> None:
        self.write_polity("some_polity")
        self.write_seshat_polities([{"seshat_id": "EgBadar", "world_region": "Africa"}])
        # Deliberately don't write the crosswalk file at all.
        p1, p2, p3 = self.patched()
        with p1, p2, p3:
            filled = run()
        self.assertEqual(filled, 0)


if __name__ == "__main__":
    unittest.main()
