"""Compute auditable, type-aware prominence scores. Browsing/ranking uses
pipeline/period_hierarchy.py's top_entities(), scoped to whatever part of
the tree is in view -- see ONTOLOGY.md's "Ranking and sizing" section."""

from __future__ import annotations

import argparse
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import yaml

from schema import CURRENT_YEAR

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"
CACHE_PATH = ROOT / "sources" / "wikidata_sitelinks.json"
REPORT_PATH = ROOT / "reports" / "prominence_summary.md"
# Peak-population sources for the population_scale component -- see
# _load_peak_populations' own docstring for why Maddison wins over HYDE
# where both cover the same polity.
MADDISON_PATH = ROOT / "sources" / "maddison_by_polity.parquet"
HYDE_POLITY_PATH = ROOT / "sources" / "hyde_pop_by_polity.parquet"
API_URL = "https://www.wikidata.org/w/api.php"
USER_AGENT = "histomap/0.1 (https://github.com/pmainguet/histomap)"
BATCH_SIZE = 50


def prominence_components(
    *,
    sitelinks: int,
    start: int,
    end: int | None,
    authority_coverage: float = 0,
    historical_evidence: float = 0,
    population: float = 0,
    current_year: int = CURRENT_YEAR,
) -> dict[str, float]:
    """Five independently capped, additive components (11 September 2026:
    dropped editorial_work, relationship_centrality, aggregate_penalty,
    type_uncertainty_penalty, and date_uncertainty_penalty -- all judged
    too brittle, mixing genuine historical prominence with how much
    curation attention a record happens to have received, or a single
    Wikidata type/confidence flag that isn't always reliable. Replaced by
    population_scale, a real magnitude signal instead of a boolean
    "is a population source tagged" proxy -- see _load_peak_populations)."""
    duration = max(1, (end if end is not None else current_year) - start)
    components = {
        "wikidata_reach": min(30, 15 * math.log10(1 + max(0, sitelinks))),
        "authority_coverage": min(20, max(0, authority_coverage)),
        "historical_evidence": min(20, max(0, historical_evidence)),
        "longevity": min(8, 2.5 * math.log10(1 + duration)),
        # Log-scaled like wikidata_reach: population spans ~7 orders of
        # magnitude across the dataset (a few hundred to ~1.4 billion), so
        # a linear scale would make every pre-modern polity a rounding
        # error next to any modern nation-state. Coefficient 2.2 reaches
        # the cap around 1-2 billion (today's largest real populations)
        # while still giving real separation in the low-thousands to
        # low-millions range most historical polities fall into.
        "population_scale": min(20, 2.2 * math.log10(1 + max(0, population))),
    }
    components["total"] = min(100, max(0, sum(components.values())))
    return {key: round(value, 2) for key, value in components.items()}


def _load_cache(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    return {str(qid): int(count) for qid, count in json.loads(path.read_text(encoding="utf-8")).items()}


def _fetch_batch(batch: list[str]) -> dict[str, int]:
    params = urlencode(
        {"action": "wbgetentities", "format": "json", "formatversion": "2", "ids": "|".join(batch), "props": "sitelinks"}
    )
    request = Request(f"{API_URL}?{params}", headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310 - fixed HTTPS endpoint
                entities = json.load(response).get("entities", {})
            return {qid: len(entities.get(qid, {}).get("sitelinks", {})) for qid in batch}
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def fetch_sitelinks(qids: list[str], cache_path: Path = CACHE_PATH) -> dict[str, int]:
    cache = _load_cache(cache_path)
    missing = sorted(set(qids) - set(cache))
    batches = [missing[index : index + BATCH_SIZE] for index in range(0, len(missing), BATCH_SIZE)]
    with ThreadPoolExecutor(max_workers=8) as executor:
        for result in (future.result() for future in as_completed([executor.submit(_fetch_batch, batch) for batch in batches])):
            cache.update(result)
            cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    return cache


def _peak_by_polity(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    frame = pd.read_parquet(path, columns=["polity_id", "population"])
    return frame.groupby("polity_id")["population"].max().astype(float).to_dict()


def _load_peak_populations(
    maddison_path: Path = MADDISON_PATH, hyde_path: Path = HYDE_POLITY_PATH
) -> tuple[dict[str, float], dict[str, str]]:
    """Peak population per polity_id, plus which source it came from (for
    the report). HYDE's per-polity estimate (pipeline/extract_hyde.py) is
    a fixed 2.5-degree centroid-radius sum -- broad coverage (every
    eligible accepted polity with a centroid) but badly undercounts
    anything territorially large, since the circle only ever captures a
    slice of a big country (the United States' 2025 HYDE figure is ~1.9
    million against a real ~335 million). Maddison Project population
    (pipeline/map_maddison.py's per-polity mapping, matched via
    present_countries) is real national population -- accurate, but only
    covers ~141 modern nation-states, 1516-2022. Maddison wins wherever
    it covers a polity; HYDE fills in everyone else."""
    peaks = _peak_by_polity(hyde_path)
    source = {polity_id: "hyde" for polity_id in peaks}
    maddison_peaks = _peak_by_polity(maddison_path)
    peaks.update(maddison_peaks)
    source.update({polity_id: "maddison" for polity_id in maddison_peaks})
    return peaks, source


def compute(
    polities_dir: Path = POLITIES_DIR,
    cache_path: Path = CACHE_PATH,
    offline: bool = False,
    report_path: Path = REPORT_PATH,
    maddison_path: Path = MADDISON_PATH,
    hyde_path: Path = HYDE_POLITY_PATH,
) -> dict[str, int]:
    paths = sorted(polities_dir.glob("*.yaml"))
    documents = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in paths]
    qids = [
        (document.get("external_ids") or {}).get("wikidata")
        for document in documents
        if (document.get("external_ids") or {}).get("wikidata")
    ]
    sitelinks = _load_cache(cache_path) if offline else fetch_sitelinks(qids, cache_path)
    if offline and set(qids) - set(sitelinks):
        raise ValueError("sitelink cache is incomplete; rerun without --offline")
    peak_population, population_source = _load_peak_populations(maddison_path, hyde_path)

    for document in documents:
        qid = (document.get("external_ids") or {}).get("wikidata")
        sources = set(document.get("sources") or [])
        authority = (12 if "seshat" in sources else 0) + (4 if "hyde" in sources else 0) + (4 if "maddison" in sources else 0)
        evidence = 20 if document.get("weight_by_era") and not document.get("weight_imputed", True) else 8 if {"hyde", "maddison"} & sources else 0
        components = prominence_components(
            sitelinks=sitelinks.get(qid, 0),
            start=document["start"],
            end=document.get("end"),
            authority_coverage=authority,
            historical_evidence=evidence,
            population=peak_population.get(document["id"], 0),
        )
        document["prominence_components"] = components
        document["prominence_score"] = components["total"]

    for path, document in zip(paths, documents, strict=True):
        path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
    scores = [document["prominence_score"] for document in documents]
    matched = [population_source.get(document["id"]) for document in documents]
    report_path.write_text(
        "# Prominence scores\n\n"
        f"- Records scored: {len(scores):,}\n"
        f"- Score range: {min(scores):.1f} - {max(scores):.1f}\n"
        f"- Mean score: {sum(scores) / len(scores):.1f}\n"
        f"- population_scale source: {matched.count('maddison'):,} from Maddison (accurate, modern "
        f"nation-states), {matched.count('hyde'):,} from HYDE (broader, coarser), "
        f"{matched.count(None):,} with no population data at all (component contributes 0).\n",
        encoding="utf-8",
    )
    return {"scored": len(scores)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Require and use the existing sitelink cache")
    args = parser.parse_args()
    result = compute(offline=args.offline)
    print(f"Scored {result['scored']} records")


if __name__ == "__main__":
    main()
