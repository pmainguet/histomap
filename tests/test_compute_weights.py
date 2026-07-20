import unittest

import pandas as pd

from pipeline.compute_weights import bucket_year, consolidate_population, normalize_weights


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

    def test_weights_are_clipped_and_missing_features_are_imputed(self) -> None:
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
        result = normalize_weights(frame, CONFIG)
        self.assertTrue(result.iloc[0]["weight_imputed"])
        self.assertTrue(result["weight"].between(1, 10).all())
        self.assertGreater(result.iloc[1]["weight"], result.iloc[0]["weight"])


if __name__ == "__main__":
    unittest.main()
