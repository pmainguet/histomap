"""Aggregate gridded HYDE population around canonical polity centroids."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "sources" / "hyde"
OUTPUT_PATH = ROOT / "sources" / "hyde_pop_by_polity.parquet"
REPORT_PATH = ROOT / "reports" / "hyde_extraction_summary.md"
POPULATION_NAMES = ("popc", "population_count", "population", "pop")
LATITUDE_NAMES = ("lat", "latitude", "y")
LONGITUDE_NAMES = ("lon", "longitude", "x")
TIME_NAMES = ("time", "year")
OUTPUT_COLUMNS = (
    "polity_id",
    "year",
    "population",
    "method",
    "radius_degrees",
    "weight_imputed",
)


def _first_name(candidates: tuple[str, ...], available: set[str], kind: str) -> str:
    for candidate in candidates:
        if candidate in available:
            return candidate
    raise ValueError(f"HYDE dataset has no recognized {kind}; found {sorted(available)}")


def inspect_dataset(dataset: xr.Dataset) -> tuple[str, str, str, str | None]:
    population = _first_name(POPULATION_NAMES, set(dataset.data_vars), "population variable")
    coordinates = set(dataset.coords) | set(dataset.dims)
    latitude = _first_name(LATITUDE_NAMES, coordinates, "latitude coordinate")
    longitude = _first_name(LONGITUDE_NAMES, coordinates, "longitude coordinate")
    time = next((name for name in TIME_NAMES if name in coordinates), None)
    return population, latitude, longitude, time


def year_from_path(path: Path) -> int | None:
    match = re.search(r"(?i)(\d{1,5})\s*(bc|bce|ad|ce)", path.stem)
    if not match:
        return None
    year = int(match.group(1))
    return -year if match.group(2).lower() in {"bc", "bce"} else year


def aggregate_radius(
    values: xr.DataArray, latitude: str, longitude: str, lat: float, lon: float, radius: float
) -> float:
    grid_lon = values[longitude]
    target_lon = lon % 360 if float(grid_lon.max()) > 180 else lon
    lat_delta = values[latitude] - lat
    lon_delta = abs(grid_lon - target_lon)
    if float(grid_lon.max()) > 180:
        lon_delta = xr.where(lon_delta > 180, 360 - lon_delta, lon_delta)
    mask = (lat_delta**2 + lon_delta**2) <= radius**2
    return float(values.where(mask).sum(skipna=True).item())


def radius_cell_indices(
    latitudes: np.ndarray,
    longitudes: np.ndarray,
    lat: float,
    lon: float,
    radius: float,
) -> np.ndarray:
    target_lon = lon % 360 if float(longitudes.max()) > 180 else lon
    lat_indices = np.flatnonzero(np.abs(latitudes - lat) <= radius)
    lon_delta = np.abs(longitudes - target_lon)
    if float(longitudes.max()) > 180:
        lon_delta = np.minimum(lon_delta, 360 - lon_delta)
    lon_indices = np.flatnonzero(lon_delta <= radius)
    if not len(lat_indices) or not len(lon_indices):
        return np.array([], dtype=np.int64)
    lat_grid, lon_grid = np.meshgrid(lat_indices, lon_indices, indexing="ij")
    distances = (latitudes[lat_grid] - lat) ** 2 + lon_delta[lon_grid] ** 2
    return (lat_grid * len(longitudes) + lon_grid)[distances <= radius**2].astype(np.int64)


def polity_points() -> list[dict]:
    points = []
    for path in (ROOT / "polities").glob("*.yaml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        centroid = (document.get("geography") or {}).get("centroid")
        if document.get("eligibility") == "accepted" and centroid:
            points.append(
                {
                    "polity_id": document["id"],
                    "start": int(document["start"]),
                    "end": document.get("end"),
                    "lat": float(centroid["lat"]),
                    "lon": float(centroid["lon"]),
                }
            )
    return points


def extract_file(path: Path, points: list[dict], radius: float, progress: bool = False) -> list[dict]:
    rows = []
    with xr.open_dataset(path) as dataset:
        population, latitude, longitude, time = inspect_dataset(dataset)
        latitudes = np.asarray(dataset[latitude].values)
        longitudes = np.asarray(dataset[longitude].values)
        indexed_points = [
            {
                **point,
                "cells": radius_cell_indices(
                    latitudes, longitudes, point["lat"], point["lon"], radius
                ),
            }
            for point in points
        ]
        slices: list[tuple[int, int | None]] = []
        if time:
            for index, raw_year in enumerate(dataset[time].values):
                year = int(getattr(raw_year, "year", raw_year))
                slices.append((year, index))
        else:
            year = dataset.attrs.get("year") or year_from_path(path)
            if year is None:
                raise ValueError(f"cannot determine year for {path.name}")
            slices.append((int(year), None))
        for position, (year, time_index) in enumerate(slices, start=1):
            active = [
                point
                for point in indexed_points
                if year >= point["start"]
                and (point["end"] is None or year <= point["end"])
                and len(point["cells"])
            ]
            if not active:
                continue
            if progress and (position == 1 or position % 10 == 0 or position == len(slices)):
                print(f"HYDE {path.name}: slice {position}/{len(slices)} ({year})", flush=True)
            values = (
                dataset[population].isel({time: time_index}).values
                if time_index is not None
                else dataset[population].values
            )
            flattened = np.asarray(values).reshape(-1)
            for point in active:
                rows.append(
                    {
                        "polity_id": point["polity_id"],
                        "year": year,
                        "population": round(float(np.nansum(flattened[point["cells"]]))),
                        "method": "centroid_radius",
                        "radius_degrees": radius,
                        "weight_imputed": True,
                    }
                )
    return rows


def run(input_dir: Path = DEFAULT_INPUT, radius: float = 2.5) -> pd.DataFrame:
    files = sorted(input_dir.rglob("*.nc")) if input_dir.exists() else []
    if not files:
        raise FileNotFoundError(f"no NetCDF files found under {input_dir}")
    points = polity_points()
    rows = [row for path in files for row in extract_file(path, points, radius, progress=True)]
    output = pd.DataFrame(rows, columns=OUTPUT_COLUMNS).sort_values(
        ["polity_id", "year"], ignore_index=True
    )
    output.to_parquet(OUTPUT_PATH, index=False)
    lines = [
        "# HYDE extraction",
        "",
        f"- NetCDF files: {len(files):,}",
        f"- Eligible polity centroids: {len(points):,}",
        f"- Polities with estimates: {output['polity_id'].nunique() if not output.empty else 0:,}",
        f"- Polity-year estimates: {len(output):,}",
        f"- Centroid radius: {radius:g} degrees",
        "",
        "All current estimates are imputed centroid-radius sums. Polygon aggregation will replace",
        "them when reviewed historical boundaries are available.",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--radius", type=float, default=2.5)
    args = parser.parse_args()
    output = run(args.input, args.radius)
    print(f"HYDE: wrote {len(output):,} polity-year population estimates")


if __name__ == "__main__":
    main()
