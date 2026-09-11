import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import yaml

from pipeline.compute_weights import (
    bucket_year,
    consolidate_population,
    load_consolidated_population,
    normalize_significance,
)


CONFIG = {
    "coefficients": {"population": 0.4, "area": 0.4, "complexity": 0.2},
    "normalization": {
        "complexity_scale": 10,
        "minimum_weight": 1,
        "maximum_weight": 10,
        "percentile": 0.95,
        "lower_percentile": 0.05,
    },
}


class WeightComputationTests(unittest.TestCase):
    def test_negative_year_buckets_are_stable(self) -> None:
        self.assertEqual(bucket_year(-1, 50), -50)
        self.assertEqual(bucket_year(-50, 50), -50)

    def test_maddison_overrides_hyde_in_the_same_bucket(self) -> None:
        hyde = pd.DataFrame({"polity_id": ["x"], "year": [1900], "population": [10]})
        maddison = pd.DataFrame({"polity_id": ["x"], "year": [1910], "population": [100]})
        result = consolidate_population(hyde, maddison, 50)
        self.assertEqual(result.iloc[0]["population"], 100)
        self.assertEqual(result.iloc[0]["population_source"], "maddison")

    def test_significance_is_clipped_and_missing_features_are_imputed(self) -> None:
        frame = pd.DataFrame(
            {
                "polity_id": ["small", "large"],
                "year": [1000, 1000],
                "population": [100, 1_000_000],
                "population_source": ["maddison", "maddison"],
                "area_km2_log10": [None, 6],
                "social_complexity_index": [None, 8],
            }
        )
        result = normalize_significance(frame, CONFIG)
        self.assertTrue(result.iloc[0]["significance_imputed"])
        self.assertTrue(result["significance"].between(1, 10).all())
        self.assertGreater(result.iloc[1]["significance"], result.iloc[0]["significance"])


class LoadConsolidatedPopulationTests(unittest.TestCase):
    """The shared Maddison-preferred-over-HYDE population merge both
    normalize_significance's own population input and
    pipeline/compute_prominence.py's population_scale component are
    built from -- see that module's _load_peak_populations."""

    def _write_fixtures(
        self,
        root: Path,
        *,
        documents: list[dict],
        hyde_rows: list[dict],
        maddison_rows: list[dict],
        direct_types: dict | None = None,
    ) -> None:
        polities_dir = root / "polities"
        polities_dir.mkdir()
        for document in documents:
            (polities_dir / f"{document['id']}.yaml").write_text(yaml.safe_dump(document), encoding="utf-8")
        sources_dir = root / "sources"
        sources_dir.mkdir()
        (sources_dir / "wikidata_direct_types.json").write_text(json.dumps(direct_types or {}), encoding="utf-8")
        pd.DataFrame(hyde_rows).to_parquet(root / "hyde.parquet")
        pd.DataFrame(maddison_rows).to_parquet(root / "maddison.parquet")

    def test_missing_parquets_return_empty_frame(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = load_consolidated_population(
                root / "no_hyde.parquet", root / "no_maddison.parquet", root, interval=50,
                type_cache_path=root / "sources" / "wikidata_direct_types.json",
            )
            self.assertTrue(result.empty)
            self.assertEqual(list(result.columns), ["polity_id", "year", "population", "population_source"])

    def test_merges_hyde_and_maddison_maddison_preferred(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixtures(
                root,
                documents=[{"id": "rome", "start": -700, "end": 476, "external_ids": {}}],
                hyde_rows=[{"polity_id": "rome", "year": 100, "population": 1_000}],
                maddison_rows=[{"polity_id": "rome", "year": 100, "population": 50_000}],
            )
            result = load_consolidated_population(
                root / "hyde.parquet", root / "maddison.parquet", root / "polities", interval=50,
                type_cache_path=root / "sources" / "wikidata_direct_types.json",
            )
            self.assertEqual(result.iloc[0]["population"], 50_000)
            self.assertEqual(result.iloc[0]["population_source"], "maddison")

    def test_unmapped_open_ended_sovereign_state_is_excluded_from_hyde(self) -> None:
        # A still-open ("end": null) sovereign state Maddison failed to
        # map should get no population signal at all -- not HYDE's
        # badly-undercounting centroid-radius number standing in for it.
        # Q6256 is Wikidata's "sovereign state" direct type (see
        # pipeline/backfill_entity_types.py's SOVEREIGN_QIDS).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixtures(
                root,
                documents=[
                    {"id": "modernia", "start": 1950, "end": None, "external_ids": {"wikidata": "Q999999"}}
                ],
                hyde_rows=[{"polity_id": "modernia", "year": 2000, "population": 500}],
                maddison_rows=[{"polity_id": "other", "year": 2000, "population": 1_000}],
                direct_types={"Q999999": {"types": ["Q6256"]}},
            )
            result = load_consolidated_population(
                root / "hyde.parquet", root / "maddison.parquet", root / "polities", interval=50,
                type_cache_path=root / "sources" / "wikidata_direct_types.json",
            )
            self.assertNotIn("modernia", set(result["polity_id"]))

    def test_mapped_sovereign_state_is_not_excluded(self) -> None:
        # Same shape as above, but Maddison DOES cover it -- no exclusion,
        # HYDE's row for it should simply be superseded per-bucket as usual.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixtures(
                root,
                documents=[
                    {"id": "modernia", "start": 1950, "end": None, "external_ids": {"wikidata": "Q999999"}}
                ],
                hyde_rows=[{"polity_id": "modernia", "year": 2000, "population": 500}],
                maddison_rows=[{"polity_id": "modernia", "year": 2000, "population": 300_000_000}],
                direct_types={"Q999999": {"types": ["Q6256"]}},
            )
            result = load_consolidated_population(
                root / "hyde.parquet", root / "maddison.parquet", root / "polities", interval=50,
                type_cache_path=root / "sources" / "wikidata_direct_types.json",
            )
            row = result[result["polity_id"] == "modernia"].iloc[0]
            self.assertEqual(row["population"], 300_000_000)
            self.assertEqual(row["population_source"], "maddison")


if __name__ == "__main__":
    unittest.main()
