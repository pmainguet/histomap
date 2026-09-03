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

    def write_polity(self, polity_id: str, canonical_name: str | None = None,
                      external_ids: dict | None = None,
                      manual_overrides: list | None = None) -> None:
        document: dict = {"id": polity_id, "canonical_name": canonical_name or polity_id}
        if external_ids is not None:
            document["external_ids"] = external_ids
        if manual_overrides is not None:
            document["manual_overrides"] = manual_overrides
        (self.root / "polities" / f"{polity_id}.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
        )

    def write_seshat_polities(self, rows: list[dict]) -> None:
        pd.DataFrame(
            rows, columns=["seshat_id", "canonical_name", "world_region"]
        ).to_parquet(self.seshat_polities_path)

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
        self.write_seshat_polities([{"seshat_id": "EgBadar", "canonical_name": "Badarian", "world_region": "Africa"}])
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
        self.write_seshat_polities([{"seshat_id": "AfKushn", "canonical_name": "Kushan Empire", "world_region": "CentralEurasia"}])
        self.write_crosswalk([])
        p1, p2, p3 = self.patched()
        with p1, p2, p3:
            run()
        document = yaml.safe_load((self.root / "polities" / "kushan_empire.yaml").read_text(encoding="utf-8"))
        self.assertEqual(document["geography"]["continents"], ["asia"])

    def test_crosswalk_fallback_when_no_own_external_id(self) -> None:
        self.write_polity("some_polity")  # no external_ids at all
        self.write_seshat_polities([{"seshat_id": "KhAngkL", "canonical_name": "Late Angkor", "world_region": "SoutheastAsia"}])
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
            {"seshat_id": "EgBadar", "canonical_name": "Badarian", "world_region": "Africa"},
            {"seshat_id": "KhAngkL", "canonical_name": "Late Angkor", "world_region": "SoutheastAsia"},
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
            {"seshat_id": "EgBadar", "canonical_name": "Badarian", "world_region": "Africa"},
            {"seshat_id": "KhAngkL", "canonical_name": "Late Angkor", "world_region": "SoutheastAsia"},
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
        self.write_seshat_polities([{"seshat_id": "EgBadar", "canonical_name": "Badarian", "world_region": "Africa"}])
        self.write_crosswalk([])
        p1, p2, p3 = self.patched()
        with p1, p2, p3:
            filled = run()
        self.assertEqual(filled, 0)

    def test_locked_geography_is_left_alone(self) -> None:
        self.write_polity(
            "locked_polity", external_ids={"seshat": "EgBadar"}, manual_overrides=["geography"],
        )
        self.write_seshat_polities([{"seshat_id": "EgBadar", "canonical_name": "Badarian", "world_region": "Africa"}])
        self.write_crosswalk([])
        p1, p2, p3 = self.patched()
        with p1, p2, p3:
            filled = run()
        self.assertEqual(filled, 0)

    def test_no_crosswalk_file_is_handled_gracefully(self) -> None:
        self.write_polity("some_polity")
        self.write_seshat_polities([{"seshat_id": "EgBadar", "canonical_name": "Badarian", "world_region": "Africa"}])
        # Deliberately don't write the crosswalk file at all.
        p1, p2, p3 = self.patched()
        with p1, p2, p3:
            filled = run()
        self.assertEqual(filled, 0)

    def test_id_suffix_match_with_matching_canonical_name_fills_continent(self) -> None:
        # No external_ids at all -- id's own last segment ("khangke") is the
        # seshat_id ("KhAngkE") lowercased, and canonical_name matches
        # exactly, same real-world shape as seshat_angkor_khangke.
        self.write_polity("seshat_angkor_khangke", canonical_name="Early Angkor")
        self.write_seshat_polities([
            {"seshat_id": "KhAngkE", "canonical_name": "Early Angkor", "world_region": "SoutheastAsia"}
        ])
        self.write_crosswalk([])
        p1, p2, p3 = self.patched()
        with p1, p2, p3:
            filled = run()
        self.assertEqual(filled, 1)
        document = yaml.safe_load(
            (self.root / "polities" / "seshat_angkor_khangke.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(document["geography"]["continents"], ["asia"])

    def test_id_suffix_match_strips_trailing_asterisks(self) -> None:
        # Seshat marks some ids with trailing "*" for uncertain dating
        # (e.g. "IqBazi*") -- stripped from both sides before comparing.
        self.write_polity("seshat_bazi_dynasty_iqbazi", canonical_name="Bazi Dynasty")
        self.write_seshat_polities([
            {"seshat_id": "IqBazi*", "canonical_name": "Bazi Dynasty", "world_region": "SouthwestAsia"}
        ])
        self.write_crosswalk([])
        p1, p2, p3 = self.patched()
        with p1, p2, p3:
            filled = run()
        self.assertEqual(filled, 1)

    def test_id_suffix_match_rejected_when_canonical_name_disagrees(self) -> None:
        # The id-suffix match alone isn't authoritative -- a name mismatch
        # means it's a coincidental collision, not a real link.
        self.write_polity("seshat_something_khangke", canonical_name="Something Else Entirely")
        self.write_seshat_polities([
            {"seshat_id": "KhAngkE", "canonical_name": "Early Angkor", "world_region": "SoutheastAsia"}
        ])
        self.write_crosswalk([])
        p1, p2, p3 = self.patched()
        with p1, p2, p3:
            filled = run()
        self.assertEqual(filled, 0)

    def test_authoritative_paths_take_precedence_over_id_suffix(self) -> None:
        # A record with its own external_ids.seshat is resolved via path 1
        # even if its id also happens to end in an unrelated seshat_id-like
        # fragment -- path 3 is only tried when 1 and 2 found nothing.
        self.write_polity(
            "some_polity_khangke", canonical_name="Some Other Polity",
            external_ids={"seshat": "EgBadar"},
        )
        self.write_seshat_polities([
            {"seshat_id": "EgBadar", "canonical_name": "Badarian", "world_region": "Africa"},
            {"seshat_id": "KhAngkE", "canonical_name": "Early Angkor", "world_region": "SoutheastAsia"},
        ])
        self.write_crosswalk([])
        p1, p2, p3 = self.patched()
        with p1, p2, p3:
            run()
        document = yaml.safe_load(
            (self.root / "polities" / "some_polity_khangke.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(document["geography"]["continents"], ["africa"])


if __name__ == "__main__":
    unittest.main()
