"""Backfill continent/country geography for entities enrich_geography.py could not resolve.

`enrich_geography.py` only has one source of truth: the cached Wikidata SPARQL extract
(`sources/wikidata.parquet`). For roughly 1,300 active entities that extract never captured
coordinates (P625) or a country (P17) at all, so they stay `unknown` forever even though more
evidence exists elsewhere. This script adds three further, explicitly-labelled evidence tiers,
applied only to active (non-retired), non-locked entities whose geography currently has neither
`continents` nor `present_countries`:

1. **Cached Wikidata reuse.** Re-run the same coordinate/country resolution enrich_geography.py
   uses, in case a record was added or reclassified after the last enrichment pass.
2. **Seshat's own classification.** Records that trace back to a Seshat polity -- via
   `external_ids.seshat`, or via the `seshat_<name>_<code>` id convention used when a
   reconciliation record was kept as a separate entity -- carry Seshat's `world_region` (maps
   cleanly to one of our seven continents) and `ngas` (Natural Geographic Area; a small, closed,
   well-documented set of 35 locations, 33 of which map to one unambiguous modern country).
   `Lowland Andes` is deliberately left without a country: unlike the other 34 NGAs it spans
   several plausible countries and guessing one would be worse than leaving it explicit.
3. **Live Wikidata fetch.** For entities with a Wikidata id that neither tier above resolved,
   batch-fetch P625 (coordinate), P17 (country), and P131 (located in admin entity, last resort
   per the caution in PLAN.md 7c) directly from the API. Results are cached to
   `sources/wikidata_geo_supplement.json` so a rerun is free and offline.

Never overwrites a manually locked geography field (`manual_overrides` containing "geography"),
and never writes a file where no new information was actually found -- an entity that stays
unresolved after all three tiers is left exactly as it was, still explicitly unknown.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import yaml
from SPARQLWrapper import JSON, SPARQLWrapper

from pipeline.enrich_geography import (
    PARQUET_PATH,
    POLITIES_DIR,
    USER_AGENT,
    country_metadata,
    field_locked,
    load_boundaries,
    locate_point,
    parse_point,
)
from pipeline.reconcile import normalize_name

ROOT = Path(__file__).resolve().parent.parent
SESHAT_PARQUET = ROOT / "sources" / "seshat_polities.parquet"
GEO_SUPPLEMENT_CACHE = ROOT / "sources" / "wikidata_geo_supplement.json"
REPORT_PATH = ROOT / "reports" / "geography_backfill_summary.md"

# Seshat's ten "world region" strata map onto our seven-continent vocabulary without ambiguity.
WORLD_REGION_CONTINENT = {
    "Africa": "africa",
    "CentralEurasia": "asia",
    "EastAsia": "asia",
    "Europe": "europe",
    "NorthAmerica": "north_america",
    "Oceania-Australia": "oceania",
    "SouthAmerica": "south_america",
    "SouthAsia": "asia",
    "SoutheastAsia": "asia",
    "SouthwestAsia": "asia",
}

# The 35 Seshat Natural Geographic Areas (the fixed "World Sample 30"-derived set used across
# the databank) mapped to one present-day ISO 3166-1 alpha-2 country. `Lowland Andes` is
# intentionally omitted -- it spans multiple plausible countries and Seshat's own documentation
# does not pin down one, so we leave it as continent-only rather than guess.
NGA_COUNTRY = {
    "Basin of Mexico": "MX",
    "Big Island Hawaii": "US",
    "Cahokia": "US",
    "Cambodian Basin": "KH",
    "Central Java": "ID",
    "Chuuk Islands": "FM",
    "Crete": "GR",
    "Cuzco": "PE",
    "Deccan": "IN",
    "Finger Lakes": "US",
    "Galilee": "IL",
    "Garo Hills": "IN",
    "Ghanaian Coast": "GH",
    "Iceland": "IS",
    "Kachi Plain": "PK",
    "Kansai": "JP",
    "Kapuasi Basin": "ID",
    "Konya Plain": "TR",
    "Latium": "IT",
    "Lena River Valley": "RU",
    "Middle Ganga": "IN",
    "Middle Yellow River Valley": "CN",
    "Niger Inland Delta": "ML",
    "North Colombia": "CO",
    "Orkhon Valley": "MN",
    "Oro PNG": "PG",
    "Paris Basin": "FR",
    "Sogdiana": "UZ",
    "Southern China Hills": "CN",
    "Southern Mesopotamia": "IQ",
    "Susiana": "IR",
    "Upper Egypt": "EG",
    "Valley of Oaxaca": "MX",
    "Yemeni Coastal Plain": "YE",
}


def is_missing_geography(document: dict) -> bool:
    geography = document.get("geography") or {}
    return not geography.get("continents") and not geography.get("present_countries")


def load_seshat_index() -> tuple[dict[str, dict], dict[str, str]]:
    """Return (seshat_id -> {world_region, ngas}, normalized seshat_id -> seshat_id)."""
    frame = pd.read_parquet(SESHAT_PARQUET, columns=["seshat_id", "world_region", "ngas"])
    by_id: dict[str, dict] = {}
    by_normalized: dict[str, str] = {}
    for row in frame.to_dict(orient="records"):
        seshat_id = str(row["seshat_id"])
        world_region = row.get("world_region")
        ngas = row.get("ngas")
        by_id[seshat_id] = {
            "world_region": None if world_region is None or pd.isna(world_region) else str(world_region),
            "ngas": [] if ngas is None else list(ngas),
        }
        by_normalized[normalize_name(seshat_id).replace(" ", "_")] = seshat_id
    return by_id, by_normalized


def find_seshat_id(document: dict, by_normalized: dict[str, str]) -> str | None:
    seshat_ids = (document.get("external_ids") or {}).get("seshat")
    if isinstance(seshat_ids, str):
        seshat_ids = [seshat_ids]
    for candidate in seshat_ids or []:
        if candidate:
            return str(candidate)
    if document["id"].startswith("seshat_"):
        trailing = document["id"].rsplit("_", 1)[-1]
        return by_normalized.get(trailing)
    return None


def _name_matches_nga(canonical_name: str, nga: str) -> bool:
    """True only when the record IS that NGA's own generic entry (e.g. "Konya Plain - Early
    Neolithic"), not merely a named state Seshat happened to code under that NGA for sampling
    convenience. A named kingdom's single assigned NGA can sit nowhere near its real territory
    (e.g. "Aksum I" is filed under Seshat's "Yemeni Coastal Plain", not Ethiopia/Eritrea) --
    trusting the NGA there would silently write wrong geography. Substring matching in either
    direction is deliberately conservative: it accepts "Archaic Crete" (contains "Crete") and
    exact matches, and rejects everything without a textual link, leaving named states that
    don't textually match to tier 3 (their own Wikidata data) instead of a guess.
    """
    name, nga_lower = canonical_name.lower(), nga.lower()
    return nga_lower in name or name in nga_lower


def geography_from_seshat(document: dict, seshat_by_id: dict, by_normalized: dict[str, str]) -> dict | None:
    seshat_id = find_seshat_id(document, by_normalized)
    if seshat_id is None or seshat_id not in seshat_by_id:
        return None
    info = seshat_by_id[seshat_id]
    canonical_name = document.get("canonical_name", "")
    matching_ngas = [nga for nga in info["ngas"] if _name_matches_nga(canonical_name, nga)]
    if not matching_ngas:
        return None
    continent = WORLD_REGION_CONTINENT.get(info["world_region"] or "")
    countries = sorted({NGA_COUNTRY[nga] for nga in matching_ngas if nga in NGA_COUNTRY})
    if not continent and not countries:
        return None
    return {
        "continents": [continent] if continent else [],
        "present_countries": countries,
        "centroid": (document.get("geography") or {}).get("centroid"),
        "confidence": "medium",
    }


SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
SPARQL_BATCH_SIZE = 200
QID_RE = re.compile(r"Q\d+$")


def _fetch_polity_geo_batch(qids: list[str]) -> dict[str, dict]:
    """One SPARQL query per batch, asking only for P625/P17/P131 -- far less payload than
    fetching each entity's full claim set over the REST API, which is what made the first
    attempt at this time out (~20s per 50-entity batch for data mostly unused)."""
    values = " ".join(f"wd:{qid}" for qid in qids)
    query = f"""
    SELECT ?item ?coord ?country ?admin WHERE {{
      VALUES ?item {{ {values} }}
      OPTIONAL {{ ?item wdt:P625 ?coord }}
      OPTIONAL {{ ?item wdt:P17 ?country }}
      OPTIONAL {{ ?item wdt:P131 ?admin }}
    }}
    """
    sparql = SPARQLWrapper(SPARQL_ENDPOINT, agent=USER_AGENT)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    rows = sparql.query().convert()["results"]["bindings"]
    result = {qid: {"point": None, "country_qids": [], "admin_qids": []} for qid in qids}
    for row in rows:
        qid = row["item"]["value"].rsplit("/", 1)[-1]
        entry = result[qid]
        if "coord" in row and entry["point"] is None:
            match = re.fullmatch(r"Point\(([-+\d.]+)\s+([-+\d.]+)\)", row["coord"]["value"])
            if match:
                entry["point"] = [float(match.group(1)), float(match.group(2))]
        for key, field in (("country", "country_qids"), ("admin", "admin_qids")):
            if key in row:
                target_qid = row[key]["value"].rsplit("/", 1)[-1]
                if QID_RE.fullmatch(target_qid) and target_qid not in entry[field]:
                    entry[field].append(target_qid)
    return result


def load_geo_supplement(qids: set[str]) -> dict[str, dict]:
    cache = json.loads(GEO_SUPPLEMENT_CACHE.read_text(encoding="utf-8")) if GEO_SUPPLEMENT_CACHE.exists() else {}
    missing = sorted(qids - set(cache))
    for index in range(0, len(missing), SPARQL_BATCH_SIZE):
        batch = missing[index : index + SPARQL_BATCH_SIZE]
        cache.update(_fetch_polity_geo_batch(batch))
        GEO_SUPPLEMENT_CACHE.parent.mkdir(parents=True, exist_ok=True)
        GEO_SUPPLEMENT_CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    return cache


def geography_from_live_fetch(qid: str, supplement: dict, boundaries: list[dict], country_meta: dict) -> dict | None:
    record = supplement.get(qid)
    if not record:
        return None
    countries: set[str] = set()
    continents: set[str] = set()
    country_qids = set(record.get("country_qids") or []) | set(record.get("admin_qids") or [])
    for target_qid in country_qids:
        info = country_meta.get(target_qid, {})
        if info.get("iso2") and len(info["iso2"]) == 2:
            countries.add(info["iso2"])
        continents.update(info.get("continents", []))
    point = record.get("point")
    located = locate_point(point[0], point[1], boundaries) if point else None
    if located:
        countries.add(located[0])
        if located[1]:
            continents.add(located[1])
    if not countries and not continents:
        return None
    confidence = "medium" if record.get("country_qids") else "low"
    return {
        "continents": sorted(continents),
        "present_countries": sorted(countries),
        "centroid": {"lat": point[1], "lon": point[0]} if point else None,
        "confidence": confidence,
    }


def run() -> dict[str, int]:
    frame = pd.read_parquet(PARQUET_PATH, columns=["qid", "coords", "country_qid"])
    cached_records = {str(row["qid"]): row for row in frame.to_dict(orient="records")}
    boundaries = load_boundaries(offline=True, high_resolution=False)
    seshat_by_id, seshat_by_normalized = load_seshat_index()

    targets = []
    for path in sorted(POLITIES_DIR.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if document.get("timeline_role") == "retired" or field_locked(document, "geography"):
            continue
        if is_missing_geography(document):
            targets.append((path, document))

    counts = {"cached_wikidata": 0, "seshat": 0, "live_wikidata": 0, "unresolved": 0}

    # Batch-resolve every country QID this tier will need in one shot, instead of one network
    # round trip per record -- that's what made the first attempt at this time out.
    cache_country_qids: set[str] = set()
    for _, document in targets:
        qid = (document.get("external_ids") or {}).get("wikidata")
        country_qid = cached_records.get(qid, {}).get("country_qid")
        if country_qid is not None and not pd.isna(country_qid):
            cache_country_qids.add(str(country_qid))
    cache_country_meta = country_metadata(cache_country_qids, offline=False) if cache_country_qids else {}

    remaining_after_cache = []
    for path, document in targets:
        qid = (document.get("external_ids") or {}).get("wikidata")
        record = cached_records.get(qid, {}) if qid else {}
        point = parse_point(record.get("coords"))
        country_qid = record.get("country_qid")
        geography = None
        if point or (country_qid is not None and not pd.isna(country_qid)):
            countries: set[str] = set()
            continents: set[str] = set()
            if country_qid is not None and not pd.isna(country_qid):
                info = cache_country_meta.get(str(country_qid), {})
                if info.get("iso2") and len(info["iso2"]) == 2:
                    countries.add(info["iso2"])
                continents.update(info.get("continents", []))
            located = locate_point(*point, boundaries) if point else None
            if located:
                countries.add(located[0])
                if located[1]:
                    continents.add(located[1])
            if countries or continents:
                geography = {
                    "continents": sorted(continents),
                    "present_countries": sorted(countries),
                    "centroid": {"lat": point[1], "lon": point[0]} if point else None,
                    "confidence": "medium" if country_qid is not None and not pd.isna(country_qid) else "low",
                }
        if geography:
            document["geography"] = geography
            path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
            counts["cached_wikidata"] += 1
        else:
            remaining_after_cache.append((path, document))

    remaining_after_seshat = []
    for path, document in remaining_after_cache:
        geography = geography_from_seshat(document, seshat_by_id, seshat_by_normalized)
        if geography:
            document["geography"] = geography
            path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
            counts["seshat"] += 1
        else:
            remaining_after_seshat.append((path, document))

    live_qids = {
        (document.get("external_ids") or {}).get("wikidata")
        for _, document in remaining_after_seshat
        if (document.get("external_ids") or {}).get("wikidata")
    }
    supplement = load_geo_supplement(live_qids) if live_qids else {}
    live_country_qids: set[str] = set()
    for record in supplement.values():
        live_country_qids.update(record.get("country_qids") or [])
        live_country_qids.update(record.get("admin_qids") or [])
    live_country_meta = country_metadata(live_country_qids, offline=False) if live_country_qids else {}
    for path, document in remaining_after_seshat:
        qid = (document.get("external_ids") or {}).get("wikidata")
        geography = (
            geography_from_live_fetch(qid, supplement, boundaries, live_country_meta) if qid else None
        )
        if geography:
            document["geography"] = geography
            path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
            counts["live_wikidata"] += 1
        else:
            counts["unresolved"] += 1

    lines = [
        "# Geography backfill",
        "",
        f"- Candidates (active, unlocked, no continent or country): {len(targets):,}",
        f"- Resolved from cached Wikidata extract: {counts['cached_wikidata']:,}",
        f"- Resolved from Seshat world_region/NGA: {counts['seshat']:,}",
        f"- Resolved from a live Wikidata fetch: {counts['live_wikidata']:,}",
        f"- Still unresolved (no usable evidence found): {counts['unresolved']:,}",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return counts


def main() -> None:
    counts = run()
    print("Geography backfill: " + ", ".join(f"{key}={value}" for key, value in counts.items()))


if __name__ == "__main__":
    main()
