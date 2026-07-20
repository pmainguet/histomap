"""Map modern Maddison observations to unambiguous canonical polities."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pandas as pd
import yaml
from rapidfuzz import fuzz
from unidecode import unidecode

ROOT = Path(__file__).resolve().parent.parent
MADDISON_PATH = ROOT / "sources" / "maddison.parquet"
BOUNDARIES_PATH = ROOT / "sources" / "ne_110m_admin_0_countries.geojson"
DIRECT_TYPES_PATH = ROOT / "sources" / "wikidata_direct_types.json"
OUTPUT_PATH = ROOT / "sources" / "maddison_by_polity.parquet"
REPORT_PATH = ROOT / "reports" / "maddison_mapping_summary.md"
PREFERRED_POLITIES = {
    "CIV": "ivory_coast",
    "LAO": "laos",
    "MKD": "north_macedonia",
    "PRK": "north_korea",
    "SWZ": "eswatini",
}


def iso2_to_iso3(path: Path = BOUNDARIES_PATH) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    mapping = {}
    for feature in data["features"]:
        properties = feature["properties"]
        iso2 = properties.get("ISO_A2")
        iso3 = properties.get("ISO_A3")
        if iso2 and iso3 and iso2 != "-99" and iso3 != "-99":
            mapping[iso2] = iso3
    return mapping


def map_document(
    document: dict,
    maddison: pd.DataFrame,
    country_codes: dict[str, str],
    sovereign_qids: set[str],
) -> tuple[str, pd.DataFrame]:
    if document.get("eligibility") != "accepted":
        return "not accepted", pd.DataFrame()
    if int(document["start"]) < 1500:
        return "pre-1500 polity", pd.DataFrame()
    if document.get("end") is not None:
        return "historical polity needs polygons", pd.DataFrame()
    qid = (document.get("external_ids") or {}).get("wikidata")
    if qid not in sovereign_qids:
        return "not directly sovereign", pd.DataFrame()
    countries = (document.get("geography") or {}).get("present_countries", [])
    if len(countries) != 1:
        return "country coverage not singular", pd.DataFrame()
    iso3 = country_codes.get(countries[0])
    if not iso3:
        return "country code unavailable", pd.DataFrame()
    selected = maddison[
        (maddison["country_code"] == iso3)
        & (maddison["year"] >= int(document["start"]))
    ].copy()
    if selected.empty:
        return "no observations in lifespan", selected
    selected.insert(0, "polity_id", document["id"])
    canonical_name = unidecode(str(document["canonical_name"])).lower()
    country_name = unidecode(str(selected.iloc[0]["country"])).lower()
    selected["match_score"] = round(float(fuzz.WRatio(canonical_name, country_name)), 2)
    selected["match_method"] = "single_present_country"
    return "mapped", selected


def run() -> pd.DataFrame:
    if not MADDISON_PATH.exists():
        raise FileNotFoundError("run pipeline/extract_maddison.py first")
    maddison = pd.read_parquet(MADDISON_PATH)
    country_codes = iso2_to_iso3()
    direct_types = json.loads(DIRECT_TYPES_PATH.read_text(encoding="utf-8"))
    sovereign_qids = {
        qid
        for qid, metadata in direct_types.items()
        if {"Q6256", "Q3624078"} & set(metadata.get("types", []))
    }
    frames = []
    decisions = Counter()
    for path in (ROOT / "polities").glob("*.yaml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        decision, mapped = map_document(document, maddison, country_codes, sovereign_qids)
        decisions[decision] += 1
        if not mapped.empty:
            frames.append(mapped)
    candidates = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if candidates.empty:
        output = candidates
    else:
        ranked = candidates[["country_code", "polity_id", "match_score"]].drop_duplicates()
        ranked["preferred"] = ranked.apply(
            lambda row: PREFERRED_POLITIES.get(row["country_code"]) == row["polity_id"], axis=1
        )
        best_polities = (
            ranked[(ranked["match_score"] >= 85) | ranked["preferred"]]
            .sort_values(
                ["country_code", "preferred", "match_score", "polity_id"],
                ascending=[True, False, False, True],
            )
            .drop_duplicates("country_code")[["country_code", "polity_id"]]
        )
        output = candidates.merge(best_polities, on=["country_code", "polity_id"], how="inner")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output.to_parquet(OUTPUT_PATH, index=False)
    lines = [
        "# Maddison polity mapping",
        "",
        f"- Candidate polities: {decisions['mapped']:,}",
        f"- Mapped polities: {output['polity_id'].nunique() if not output.empty else 0:,}",
        f"- Output observations: {len(output):,}",
        "- Method: accepted extant polity, start year 1500 or later, exactly one present-day country",
        "",
        "## Decisions",
        "",
    ]
    lines.extend(f"- {decision.title()}: {count:,}" for decision, count in sorted(decisions.items()))
    lines.extend(
        [
            "",
            "This is a modern-country proxy. Historical and multi-country polities are deliberately",
            "skipped until polygons support defensible population allocation.",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    result = run()
    print(f"Maddison mapping: wrote {len(result):,} polity-year observations")
