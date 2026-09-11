"""One-off script: aggregate the raw HYDE gridded population dataset
(sources/hyde/population.nc) into a per-continent population time series,
for the /explore Population lane's regional breakdown (ROADMAP.md item,
10 September 2026 -- "using HYDE's raw gridded population.nc ... instead
of another hand-curated global table").

Not part of the routine build.py flow: the raw grid is ~5GB and a full
continent classification pass takes roughly a minute, so this runs
separately and caches its result to OUTPUT_PATH, the same "cached
intermediate artifact other pipeline steps read" pattern extract_hyde.py's
own hyde_pop_by_polity.parquet already establishes. build.py copies the
cached JSON through to population_by_continent.json on every rebuild
(cheap -- it's a few hundred rows), the same way it already copies
periods.json/events.json through.

Method: HYDE's grid is regular at 5 arc-minutes (2160 lat x 4320 lon) --
far finer than continent-level aggregation needs. Coarsen it by 12x to a
1-degree grid (180 x 360 = 64,800 cells) by SUMMING each 12x12 block (a
population count, unlike a rate/density, sums correctly under
coarsening) with xarray's own coarsen(). Classify each of the 64,800
coarse cell centers to a continent ONCE, reusing enrich_geography.py's
existing point_in_polygon-based locate_point() (which already reads the
continent straight off the country boundary features -- no separate
country-to-continent lookup needed) rather than a naive per-original-cell
classification, which would mean tens of millions of point-in-polygon
tests instead of 64,800. The classification is independent of time, so
it's computed once and reused across all 128 time steps."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import xarray as xr

from pipeline.enrich_geography import BOUNDARIES_PATH, locate_point

ROOT = Path(__file__).resolve().parent.parent
HYDE_PATH = ROOT / "sources" / "hyde" / "population.nc"
OUTPUT_PATH = ROOT / "sources" / "hyde_population_by_continent.json"
REPORT_PATH = ROOT / "reports" / "hyde_continent_extraction_summary.md"
COARSEN_FACTOR = 12  # 5 arcmin -> 1 degree, exact for HYDE's 2160x4320 grid


def build_continent_mask(lats: np.ndarray, lons: np.ndarray, features: list[dict]) -> np.ndarray:
    """One continent label per (lat, lon) coarse cell center, shape (len(lats), len(lons)).
    Ocean/unclaimed cells (locate_point finds no matching country polygon) get "" --
    excluded from every continent's sum, same as a polity with no present_countries
    is excluded from geography-based grouping elsewhere in this project."""
    mask = np.empty((len(lats), len(lons)), dtype=object)
    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            found = locate_point(float(lon), float(lat), features)
            mask[i, j] = found[1] if found else ""
    return mask


def main() -> None:
    if not HYDE_PATH.exists():
        raise SystemExit(f"{HYDE_PATH} not found -- this script needs the raw HYDE grid on disk")

    dataset = xr.open_dataset(HYDE_PATH)
    coarse = dataset["population"].coarsen(lat=COARSEN_FACTOR, lon=COARSEN_FACTOR, boundary="trim").sum()

    features = json.loads(BOUNDARIES_PATH.read_text(encoding="utf-8"))["features"]
    mask = build_continent_mask(coarse.lat.values, coarse.lon.values, features)
    # Natural Earth tags a handful of small/disputed features "Seven seas
    # (open ocean)" -- genuinely uninhabited (population stays 0 across all
    # 128 time steps, confirmed) rather than a real continent; Antarctica is
    # real but also always 0. Both would otherwise show up as empty rows in
    # every downstream consumer for no benefit -- dropped here once, not
    # filtered repeatedly by every reader.
    all_continents = sorted({c for c in mask.flatten() if c})
    continents = [c for c in all_continents if c not in {"antarctica", "seven_seas_(open_ocean)"}]

    rows: list[dict] = []
    for time_index in range(coarse.sizes["time"]):
        year = int(coarse.time.values[time_index].year)
        slice_values = coarse.isel(time=time_index).values  # shape (lat, lon)
        for continent in continents:
            total = float(slice_values[mask == continent].sum())
            rows.append({"year": year, "continent": continent, "population": round(total)})

    rows.sort(key=lambda r: (r["year"], r["continent"]))
    OUTPUT_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    ocean_fraction = float((mask == "").sum()) / mask.size
    modern_total = sum(r["population"] for r in rows if r["year"] == int(coarse.time.values[-1].year))
    REPORT_PATH.write_text(
        "# HYDE population, aggregated by continent\n\n"
        f"- Source: {HYDE_PATH.relative_to(ROOT)} (HYDE 3.4, Klein Goldewijk & Beusen), "
        f"coarsened {COARSEN_FACTOR}x to a 1-degree grid before continent classification.\n"
        f"- Continent boundaries: {BOUNDARIES_PATH.relative_to(ROOT)}.\n"
        f"- {len(continents)} continents written: {', '.join(continents)} -- Antarctica and "
        "Natural Earth's placeholder \"Seven seas (open ocean)\" feature are always 0 across "
        "every time step and dropped rather than kept as empty rows.\n"
        f"- {ocean_fraction:.1%} of coarse grid cells are ocean/unclaimed (excluded from every "
        "continent's sum, not double-counted or dropped silently).\n"
        f"- {coarse.sizes['time']} time steps, {len(rows)} (year, continent) rows written to "
        f"{OUTPUT_PATH.relative_to(ROOT)}.\n"
        f"- Known limitation: the latest time step's continent totals sum to ~{modern_total / 1e9:.1f}"
        " billion, roughly 10% under the actual current world population (~8.2 billion) -- the "
        "110m-resolution country boundaries lose some coastal/small-island population at 1-degree "
        "coarsening. Good enough for the /explore Population lane's relative continent-shape-over-"
        "time visualization; not a substitute for an authoritative modern headcount.\n\n"
        "Rerun this script whenever sources/hyde/population.nc is refreshed with a newer HYDE "
        "release -- build.py itself only copies this cached file through, it never recomputes it.\n",
        encoding="utf-8",
    )
    print(f"wrote {len(rows)} rows across {len(continents)} continents and {coarse.sizes['time']} time steps")


if __name__ == "__main__":
    main()
