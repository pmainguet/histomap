import tempfile
import unittest
from pathlib import Path

import numpy as np
import xarray as xr

from pipeline.extract_hyde import (
    aggregate_radius,
    extract_file,
    inspect_dataset,
    radius_cell_indices,
    year_from_path,
)


class HydeExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = xr.Dataset(
            {"popc": (("time", "lat", "lon"), np.array([[[1, 2], [3, 4]]]))},
            coords={"time": [1000], "lat": [0.0, 1.0], "lon": [10.0, 11.0]},
        )

    def test_inspects_common_hyde_names(self) -> None:
        self.assertEqual(inspect_dataset(self.dataset), ("popc", "lat", "lon", "time"))

    def test_radius_sum_uses_population_counts(self) -> None:
        values = self.dataset["popc"].sel(time=1000)
        self.assertEqual(aggregate_radius(values, "lat", "lon", 0, 10, 1.1), 6)

    def test_precomputes_the_same_radius_cells(self) -> None:
        cells = radius_cell_indices(
            self.dataset.lat.values, self.dataset.lon.values, 0, 10, 1.1
        )
        self.assertEqual(cells.tolist(), [0, 1, 2])

    def test_extracts_only_years_in_polity_lifespan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hyde.nc"
            self.dataset.to_netcdf(path)
            points = [{"polity_id": "test", "start": 900, "end": 1100, "lat": 0, "lon": 10}]
            rows = extract_file(path, points, 1.1)
        self.assertEqual(rows[0]["population"], 6)
        self.assertTrue(rows[0]["weight_imputed"])

    def test_reads_bce_year_from_filename(self) -> None:
        self.assertEqual(year_from_path(Path("popc_4000BC.nc")), -4000)


if __name__ == "__main__":
    unittest.main()
