import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pipeline.compute_prominence import _load_peak_populations, prominence_components


class ProminenceComponentsTests(unittest.TestCase):
    def test_components_are_capped_and_sum_to_total(self) -> None:
        components = prominence_components(
            sitelinks=100_000,
            start=-10_000,
            end=None,
            authority_coverage=50,
            historical_evidence=50,
            population=10_000_000_000,
        )
        self.assertEqual(components["wikidata_reach"], 30)
        self.assertEqual(components["authority_coverage"], 20)
        self.assertEqual(components["historical_evidence"], 20)
        self.assertEqual(components["longevity"], 8)
        self.assertEqual(components["population_scale"], 20)
        self.assertEqual(components["total"], 98)

    def test_only_five_components_plus_total(self) -> None:
        # 11 September 2026: editorial_work, relationship_centrality,
        # aggregate_penalty, type_uncertainty_penalty, and
        # date_uncertainty_penalty were all dropped as too brittle --
        # mixing genuine historical prominence with curation-attention
        # artifacts or a single not-always-reliable confidence/type flag.
        components = prominence_components(sitelinks=50, start=1000, end=1500)
        self.assertEqual(
            set(components),
            {"wikidata_reach", "authority_coverage", "historical_evidence", "longevity", "population_scale", "total"},
        )

    def test_population_scale_increases_with_population(self) -> None:
        low = prominence_components(sitelinks=0, start=1000, end=1500, population=1_000)
        high = prominence_components(sitelinks=0, start=1000, end=1500, population=100_000_000)
        self.assertLess(low["population_scale"], high["population_scale"])

    def test_no_population_data_contributes_zero(self) -> None:
        components = prominence_components(sitelinks=0, start=1000, end=1500, population=0)
        self.assertEqual(components["population_scale"], 0)


class LoadPeakPopulationsTests(unittest.TestCase):
    def test_maddison_wins_over_hyde_when_both_cover_a_polity(self) -> None:
        # HYDE's centroid-radius figure badly undercounts territorially
        # large modern states -- Maddison's real national population is
        # preferred wherever both cover the same polity_id.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hyde_path = root / "hyde.parquet"
            maddison_path = root / "maddison.parquet"
            pd.DataFrame(
                {"polity_id": ["united_states", "united_states"], "population": [1_800_000, 1_900_000]}
            ).to_parquet(hyde_path)
            pd.DataFrame(
                {"polity_id": ["united_states", "united_states"], "population": [300_000_000, 335_000_000]}
            ).to_parquet(maddison_path)
            peaks, source = _load_peak_populations(maddison_path, hyde_path)
            self.assertEqual(peaks["united_states"], 335_000_000)
            self.assertEqual(source["united_states"], "maddison")

    def test_hyde_fills_in_polities_maddison_does_not_cover(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hyde_path = root / "hyde.parquet"
            maddison_path = root / "maddison.parquet"
            pd.DataFrame({"polity_id": ["ancient_carthage"], "population": [250_000]}).to_parquet(hyde_path)
            pd.DataFrame({"polity_id": ["united_states"], "population": [335_000_000]}).to_parquet(maddison_path)
            peaks, source = _load_peak_populations(maddison_path, hyde_path)
            self.assertEqual(peaks["ancient_carthage"], 250_000)
            self.assertEqual(source["ancient_carthage"], "hyde")

    def test_missing_files_return_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            peaks, source = _load_peak_populations(root / "no_maddison.parquet", root / "no_hyde.parquet")
            self.assertEqual(peaks, {})
            self.assertEqual(source, {})


if __name__ == "__main__":
    unittest.main()
