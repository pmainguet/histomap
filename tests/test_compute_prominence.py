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
    """_load_peak_populations delegates to pipeline/compute_weights.py's
    own load_consolidated_population (see that module's tests for the
    Maddison-over-HYDE merge behavior itself) and just takes each
    polity's peak population from the merged result -- these tests cover
    that peak-taking, not the merge logic, which isn't duplicated here."""

    def _kwargs(self, root: Path) -> dict:
        polities_dir = root / "polities"
        polities_dir.mkdir(exist_ok=True)
        return {
            "hyde_path": root / "hyde.parquet",
            "maddison_path": root / "maddison.parquet",
            "polities_dir": polities_dir,
            "interval": 50,
            "type_cache_path": root / "sources" / "wikidata_direct_types.json",  # doesn't exist -- no exclusions
        }

    def test_takes_each_polity_s_peak_population(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kwargs = self._kwargs(root)
            pd.DataFrame(
                {"polity_id": ["rome", "rome"], "year": [100, 200], "population": [1_000, 1_900]}
            ).to_parquet(kwargs["hyde_path"])
            pd.DataFrame({"polity_id": [], "year": [], "population": []}).to_parquet(kwargs["maddison_path"])
            peaks, source = _load_peak_populations(**kwargs)
            self.assertEqual(peaks["rome"], 1_900)
            self.assertEqual(source["rome"], "hyde")

    def test_maddison_preferred_source_surfaces_in_the_peak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kwargs = self._kwargs(root)
            pd.DataFrame(
                {"polity_id": ["united_states"], "year": [2000], "population": [1_900_000]}
            ).to_parquet(kwargs["hyde_path"])
            pd.DataFrame(
                {"polity_id": ["united_states"], "year": [2000], "population": [335_000_000]}
            ).to_parquet(kwargs["maddison_path"])
            peaks, source = _load_peak_populations(**kwargs)
            self.assertEqual(peaks["united_states"], 335_000_000)
            self.assertEqual(source["united_states"], "maddison")

    def test_missing_files_return_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kwargs = self._kwargs(root)
            # hyde_path/maddison_path point at files that were never written.
            peaks, source = _load_peak_populations(**kwargs)
            self.assertEqual(peaks, {})
            self.assertEqual(source, {})


if __name__ == "__main__":
    unittest.main()
