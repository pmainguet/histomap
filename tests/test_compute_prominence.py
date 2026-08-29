import tempfile
import unittest
from pathlib import Path

import yaml

from pipeline.compute_prominence import compute, prominence_components, score_prominence


def document(entity_id: str, score: float, **overrides: object) -> dict:
    value = {
        "id": entity_id,
        "canonical_name": entity_id.replace("_", " ").title(),
        "start": 1000,
        "end": 1500,
        "entity_type": "polity",
        "entity_type_confidence": "high",
        "eligibility": "accepted",
        "geography": {"continents": ["europe"], "primary_continent": "europe"},
        "prominence_score": score,
        "prominence_components": {},
        "visibility_tier": "detailed",
        "external_ids": {},
    }
    value.update(overrides)
    return value


class ProminenceComponentsTests(unittest.TestCase):
    def test_components_are_capped_and_sum_to_total(self) -> None:
        components = prominence_components(
            sitelinks=100_000,
            start=-10_000,
            end=None,
            authority_coverage=50,
            historical_evidence=50,
            relationship_degree=1_000,
            transition_count=20,
            editorial_score=50,
        )
        self.assertEqual(components["wikidata_reach"], 30)
        self.assertEqual(components["authority_coverage"], 20)
        self.assertEqual(components["historical_evidence"], 20)
        self.assertEqual(components["relationship_centrality"], 15)
        self.assertEqual(components["longevity"], 8)
        self.assertEqual(components["editorial_work"], 7)
        self.assertEqual(components["total"], 100)

    def test_present_country_does_not_imply_subordination(self) -> None:
        common = dict(sitelinks=25, start=1800, end=None, authoritative=False, editorial=False)
        self.assertEqual(
            score_prominence(**common, has_parent_country=False),
            score_prominence(**common, has_parent_country=True),
        )

    def test_uncertainty_and_aggregate_penalties_are_explicit(self) -> None:
        certain = prominence_components(sitelinks=50, start=1000, end=1500)
        uncertain = prominence_components(
            sitelinks=50,
            start=1000,
            end=1500,
            entity_type_confidence="low",
            start_confidence="legendary",
            end_confidence="low",
            aggregate=True,
        )
        self.assertEqual(uncertain["type_uncertainty_penalty"], -10)
        self.assertEqual(uncertain["date_uncertainty_penalty"], -5)
        self.assertEqual(uncertain["aggregate_penalty"], -25)
        self.assertGreater(certain["total"], uncertain["total"])


class ComputeDoesNotTouchVisibilityTierTests(unittest.TestCase):
    def test_visibility_tier_is_left_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            polities_dir = Path(tmp) / "polities"
            polities_dir.mkdir()
            cache_path = Path(tmp) / "sitelinks.json"
            doc = document("test_polity", score=0)
            doc["visibility_tier"] = "global"  # deliberately pre-set, no wikidata id -> offline-safe
            (polities_dir / "test_polity.yaml").write_text(
                yaml.safe_dump(doc, sort_keys=False), encoding="utf-8"
            )

            compute(polities_dir=polities_dir, cache_path=cache_path, offline=True)

            written = yaml.safe_load((polities_dir / "test_polity.yaml").read_text(encoding="utf-8"))
            self.assertEqual(written["visibility_tier"], "global")  # unchanged
            self.assertIn("prominence_score", written)  # still recomputed


if __name__ == "__main__":
    unittest.main()
