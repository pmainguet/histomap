"""One-off pass for ROADMAP.md's geography-gaps item: fill a still-missing
`continents` value from Seshat's own `world_region` field, for records with
no Wikidata QID at all (where every other signal in this pipeline has
nothing to work from).

`sources/seshat_polities.parquet` carries a `world_region` per Seshat
polity (10 values: Africa, CentralEurasia, EastAsia, Europe, NorthAmerica,
Oceania-Australia, SouthAmerica, SouthAsia, SoutheastAsia, SouthwestAsia) --
never wired into geography before. Confirmed live, 3 September 2026:
`CentralEurasia` covers only Central Asian/Mongolian/Siberian steppe
entities (Kushan Empire, Mongol Empire, Xiongnu, Sogdiana, Sakha/Yakutia,
...), never Europe, so it maps to `asia` alongside the other four Asian
world regions -- confirmed by inspecting every CentralEurasia record's own
name, not guessed from the label.

Three ways a gap record links to a Seshat polity, tried in order:
1. Its own `external_ids.seshat` code matches `seshat_polities.parquet`'s
   `seshat_id` directly (45 records, confirmed live).
2. It has no `external_ids.seshat` of its own, but
   `sources/seshat_crosswalk.parquet` (built for the Phase 2 Seshat
   reconciliation overlay, `seshat_id -> polity_id`) links it anyway.
3. Its Histomap `id`'s last underscore-separated segment IS the
   `seshat_id`, lowercased with non-alphanumeric characters (Seshat marks
   some ids with trailing `*` for uncertain dating) stripped -- e.g. id
   `seshat_angkor_khangke` against `seshat_id` "KhAngkE". A leftover from
   how these records' ids were originally generated, but their
   `external_ids.seshat` was never actually populated -- effectively a
   data-completeness bug upstream of geography, not a fuzzy name match.
   Confirmed live, 3 September 2026: 68 of the ~68 no-QID, no-Seshat-link
   records match this way, EVERY one with an exact `canonical_name` match
   too (spot-checked all 68 by hand) -- required here as an extra
   verification gate before trusting the id-suffix alone, since unlike
   paths 1-2 this one isn't backed by an authoritative field.

Same "only fill what's missing, respect manual_overrides" convention as
every other pass in `pipeline/enrich_geography.py`. Confidence "low" --
inferred from a world region, not an asserted country.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import yaml

from pipeline.enrich_geography import field_locked

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"
SESHAT_POLITIES_PATH = ROOT / "sources" / "seshat_polities.parquet"
SESHAT_CROSSWALK_PATH = ROOT / "sources" / "seshat_crosswalk.parquet"

WORLD_REGION_TO_CONTINENT: dict[str, str] = {
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


def normalize_id_fragment(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def load_seshat_polities() -> list[dict]:
    return pd.read_parquet(
        SESHAT_POLITIES_PATH, columns=["seshat_id", "canonical_name", "world_region"]
    ).to_dict(orient="records")


def load_seshat_id_to_continent(rows: list[dict]) -> dict[str, str]:
    """seshat_id -> continent, via world_region. A seshat_id whose
    world_region isn't in WORLD_REGION_TO_CONTINENT (shouldn't happen given
    the 10 known values, but new Seshat data could add one) is skipped
    rather than guessed."""
    result = {}
    for row in rows:
        continent = WORLD_REGION_TO_CONTINENT.get(row["world_region"])
        if continent:
            result[row["seshat_id"]] = continent
    return result


def load_normalized_id_to_seshat(rows: list[dict]) -> dict[str, dict]:
    """normalized(seshat_id) -> the Seshat row, for the id-suffix match
    (path 3). Keyed on the normalized form since a Histomap id has already
    stripped case and punctuation (e.g. "IqBazi*" -> "iqbazi")."""
    return {normalize_id_fragment(row["seshat_id"]): row for row in rows}


def load_polity_id_to_seshat_ids() -> dict[str, list[str]]:
    """polity_id -> [seshat_id, ...], from the crosswalk -- the fallback
    for a record with no external_ids.seshat of its own."""
    if not SESHAT_CROSSWALK_PATH.exists():
        return {}
    frame = pd.read_parquet(SESHAT_CROSSWALK_PATH, columns=["seshat_id", "polity_id"])
    result: dict[str, list[str]] = {}
    for row in frame.to_dict(orient="records"):
        result.setdefault(row["polity_id"], []).append(row["seshat_id"])
    return result


def own_seshat_ids(document: dict) -> list[str]:
    value = (document.get("external_ids") or {}).get("seshat")
    if not value:
        return []
    return value if isinstance(value, list) else [value]


def continent_via_id_suffix(document: dict, normalized_to_seshat: dict[str, dict]) -> str | None:
    """Path 3: match the Histomap id's last segment against a normalized
    Seshat id, gated on an exact (casefolded, whitespace-trimmed)
    canonical_name match -- the id-suffix alone isn't an authoritative
    field, so this extra check is required before trusting it."""
    suffix = normalize_id_fragment(document["id"].rsplit("_", 1)[-1])
    row = normalized_to_seshat.get(suffix)
    if not row:
        return None
    own_name = str(document.get("canonical_name", "")).casefold().strip()
    seshat_name = str(row["canonical_name"]).casefold().strip()
    if own_name != seshat_name:
        return None
    return WORLD_REGION_TO_CONTINENT.get(row["world_region"])


def run() -> int:
    rows = load_seshat_polities()
    seshat_id_to_continent = load_seshat_id_to_continent(rows)
    normalized_to_seshat = load_normalized_id_to_seshat(rows)
    polity_id_to_seshat_ids = load_polity_id_to_seshat_ids()
    filled = 0
    for path in POLITIES_DIR.glob("*.yaml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if field_locked(document, "geography"):
            continue
        if (document.get("geography") or {}).get("continents"):
            continue
        seshat_ids = own_seshat_ids(document) or polity_id_to_seshat_ids.get(document["id"], [])
        continents = {
            seshat_id_to_continent[seshat_id]
            for seshat_id in seshat_ids
            if seshat_id in seshat_id_to_continent
        }
        if not continents:
            id_suffix_continent = continent_via_id_suffix(document, normalized_to_seshat)
            if id_suffix_continent:
                continents = {id_suffix_continent}
        if len(continents) != 1:
            continue
        geography = document.get("geography") or {}
        geography["continents"] = sorted(continents)
        geography.setdefault("confidence", "low")
        document["geography"] = geography
        path.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        filled += 1
    return filled


if __name__ == "__main__":
    print(f"filled: {run()}")
