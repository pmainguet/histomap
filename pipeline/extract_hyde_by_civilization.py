"""One-off script: aggregate the raw HYDE gridded population dataset
(sources/hyde/population.nc) into a per-civilization-entity population
time series, for pipeline/poster.py's population-driven band width
(ROADMAP.md item -- "leveraging [the regional population breakdown] for a
better representation of the lane in the SVG poster representation",
narrowed to the Civilizations & Cultures entity types per explicit
request, 11 September 2026: "I need to have population by year ... to be
able to draw the width of the civilization lane in the SVG").

Not part of the routine build.py flow: same "cached intermediate
artifact" pattern as extract_hyde_by_continent.py and extract_hyde.py's
own hyde_pop_by_polity.parquet -- this runs separately and caches its
result to OUTPUT_PATH; build.py copies the cached JSON through on every
rebuild (cheap, a few hundred rows).

Method: the same coarsened 1-degree grid and point-in-polygon
classification as extract_hyde_by_continent.py, but classified by ISO2
country code (not continent), so each entity's own present_countries
list selects its cells directly -- no separate country-to-continent
lookup, and no need to re-derive a bounding region per entity. Only
entities tagged with one of the /explore Civilizations & Cultures lane's
own entity_types (see build_explore_tree.py's CIVILIZATION_ENTITY_TYPES),
eligibility "accepted", with a non-empty present_countries, are
extracted -- one with no present_countries has nothing to mask against
and is reported as skipped, not silently dropped. Each entity's own
[start, end] bounds which HYDE years count (end: null -- e.g. a people
with no recorded end date -- means every HYDE year from `start` onward).

Known limitation, the mirror image of extract_hyde_by_continent.py's
~10% undercount: this masks by *modern* country borders, so it counts
the *entire* HYDE population of every present_countries country during
the entity's active years, not just the historical sub-region that
entity actually occupied -- a systematic overcount for any entity that
only used part of a large modern country's territory (the Maya heartland
is a fraction of Mexico, but this counts all of Mexico's HYDE population
as "Zapotec civilization" or similar). Fine as a *relative* width signal
for the poster (which years look bigger than others for the same
entity), not a headcount or a cross-entity population comparison."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import xarray as xr
import yaml

from pipeline.enrich_geography import BOUNDARIES_PATH, locate_point

ROOT = Path(__file__).resolve().parent.parent
HYDE_PATH = ROOT / "sources" / "hyde" / "population.nc"
OUTPUT_PATH = ROOT / "sources" / "hyde_population_by_civilization.json"
REPORT_PATH = ROOT / "reports" / "hyde_civilization_extraction_summary.md"
COARSEN_FACTOR = 12  # 5 arcmin -> 1 degree, exact for HYDE's 2160x4320 grid
# Mirrors build_explore_tree.py's CIVILIZATION_ENTITY_TYPES -- the /explore
# Civilizations & Cultures lane's own entity_type set. Not imported directly
# to avoid pulling that module's much larger dependency surface into a
# one-off extraction script; kept as a literal, same as that module's own
# comment recommends checking against if it ever changes.
CIVILIZATION_ENTITY_TYPES = {"civilization", "culture", "people", "tribe", "archaeological_horizon"}


def build_country_mask(lats: np.ndarray, lons: np.ndarray, features: list[dict]) -> np.ndarray:
    """One ISO2 country code per (lat, lon) coarse cell center, shape
    (len(lats), len(lons)). Ocean/unclaimed cells get "" -- excluded from
    every entity's sum, same treatment as extract_hyde_by_continent.py's
    continent mask."""
    mask = np.empty((len(lats), len(lons)), dtype=object)
    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            found = locate_point(float(lon), float(lat), features)
            mask[i, j] = found[0] if found else ""  # locate_point already uppercases the ISO2
    return mask


def civilization_entities() -> list[dict]:
    entities = []
    for path in sorted((ROOT / "polities").glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if document.get("entity_type") not in CIVILIZATION_ENTITY_TYPES:
            continue
        if document.get("eligibility") != "accepted":
            continue
        countries = ((document.get("geography") or {}).get("present_countries")) or []
        if not countries:
            continue
        entities.append(
            {
                "id": document["id"],
                "start": int(document["start"]),
                "end": document.get("end"),
                "countries": {str(code).upper() for code in countries},
            }
        )
    return entities


def main() -> None:
    if not HYDE_PATH.exists():
        raise SystemExit(f"{HYDE_PATH} not found -- this script needs the raw HYDE grid on disk")

    entities = civilization_entities()
    if not entities:
        raise SystemExit("no eligible civilization-type entities with present_countries found")

    dataset = xr.open_dataset(HYDE_PATH)
    coarse = dataset["population"].coarsen(lat=COARSEN_FACTOR, lon=COARSEN_FACTOR, boundary="trim").sum()

    features = json.loads(BOUNDARIES_PATH.read_text(encoding="utf-8"))["features"]
    mask = build_country_mask(coarse.lat.values, coarse.lon.values, features)

    years = [int(coarse.time.values[i].year) for i in range(coarse.sizes["time"])]
    values_by_year = {year: coarse.isel(time=i).values for i, year in enumerate(years)}

    rows: list[dict] = []
    unmatched: list[str] = []
    for entity in entities:
        cell_selector = np.isin(mask, list(entity["countries"]))
        if not cell_selector.any():
            unmatched.append(entity["id"])
            continue
        for year in years:
            if year < entity["start"]:
                continue
            if entity["end"] is not None and year > entity["end"]:
                continue
            total = float(values_by_year[year][cell_selector].sum())
            rows.append({"entity_id": entity["id"], "year": year, "population": round(total)})

    rows.sort(key=lambda r: (r["entity_id"], r["year"]))
    OUTPUT_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    covered = sorted({r["entity_id"] for r in rows})
    no_years_matched = sorted(e["id"] for e in entities if e["id"] not in covered and e["id"] not in unmatched)
    REPORT_PATH.write_text(
        "# HYDE population, aggregated by civilization entity\n\n"
        f"- Source: {HYDE_PATH.relative_to(ROOT)} (HYDE 3.4, Klein Goldewijk & Beusen), coarsened "
        f"{COARSEN_FACTOR}x to a 1-degree grid, classified by ISO2 country code using the same "
        f"point-in-polygon boundaries as extract_hyde_by_continent.py ({BOUNDARIES_PATH.relative_to(ROOT)}).\n"
        f"- {len(entities)} eligible entities considered (entity_type in "
        f"{sorted(CIVILIZATION_ENTITY_TYPES)}, eligibility accepted, present_countries set).\n"
        f"- {len(covered)} entities got a population time series.\n"
        + (f"- {len(unmatched)} entities' present_countries matched no HYDE grid cell at all: "
           f"{', '.join(unmatched)}.\n" if unmatched else "")
        + (f"- {len(no_years_matched)} entities matched cells but had no HYDE sample year inside "
           f"their [start, end]: {', '.join(no_years_matched)}.\n" if no_years_matched else "")
        + f"- {len(rows)} (entity, year) rows written to {OUTPUT_PATH.relative_to(ROOT)}, one row per "
          "HYDE sample year within each entity's own [start, end] (end: null means every HYDE year "
          "from start onward).\n\n"
        "Known limitation: this masks by *modern* country borders, not a historical territorial "
        "boundary -- it counts the *entire* HYDE population of every present_countries country "
        "during the entity's active years, a systematic overcount for any entity that only occupied "
        "part of a large modern country (e.g. the Maya heartland is a fraction of Mexico's "
        "territory, but this counts all of Mexico's HYDE population). Useful as a *relative* width "
        "signal for pipeline/poster.py's population-driven band width -- which years look bigger "
        "than others for the *same* entity -- not a headcount or a reliable cross-entity comparison.\n\n"
        "Rerun this script whenever sources/hyde/population.nc is refreshed, or when a "
        "civilization-type entity's present_countries/start/end changes -- build.py itself only "
        "copies this cached file through, it never recomputes it.\n",
        encoding="utf-8",
    )
    print(f"wrote {len(rows)} rows across {len(covered)}/{len(entities)} civilization entities")


if __name__ == "__main__":
    main()
