"""Compute auditable, type-aware prominence and balanced visibility tiers."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import yaml

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"
CACHE_PATH = ROOT / "sources" / "wikidata_sitelinks.json"
TYPE_CACHE_PATH = ROOT / "sources" / "wikidata_direct_types.json"
TRANSITIONS_PATH = ROOT / "transitions.yaml"
REPORT_PATH = ROOT / "reports" / "prominence_summary.md"
API_URL = "https://www.wikidata.org/w/api.php"
USER_AGENT = "histomap/0.1 (https://github.com/pmainguet/histomap)"
BATCH_SIZE = 50
GLOBAL_ABSOLUTE_COUNT = 60
GLOBAL_PER_STRATUM = 2
REGIONAL_ABSOLUTE_COUNT = 600
REGIONAL_PER_STRATUM = 20
CONTEXT_TYPES = {
    "subdivision", "micronation", "culture", "people", "tribe", "archaeological_horizon"
}
NORMAL_TYPES = {"polity", "civilization"}


def prominence_components(
    *,
    sitelinks: int,
    start: int,
    end: int | None,
    authority_coverage: float = 0,
    historical_evidence: float = 0,
    relationship_degree: int = 0,
    transition_count: int = 0,
    editorial_score: float = 0,
    entity_type_confidence: str = "high",
    start_confidence: str = "high",
    end_confidence: str = "high",
    aggregate: bool = False,
    current_year: int = 2026,
) -> dict[str, float]:
    duration = max(1, (end if end is not None else current_year) - start)
    components = {
        "wikidata_reach": min(30, 15 * math.log10(1 + max(0, sitelinks))),
        "authority_coverage": min(20, max(0, authority_coverage)),
        "historical_evidence": min(20, max(0, historical_evidence)),
        "relationship_centrality": min(
            15,
            3.5 * math.log2(1 + max(0, relationship_degree))
            + 3 * max(0, transition_count),
        ),
        "longevity": min(8, 2.5 * math.log10(1 + duration)),
        "editorial_work": min(7, max(0, editorial_score)),
        "type_uncertainty_penalty": -10 if entity_type_confidence == "low" else 0,
        "date_uncertainty_penalty": -2.5
        * sum(value in {"low", "legendary"} for value in (start_confidence, end_confidence)),
        "aggregate_penalty": -25 if aggregate else 0,
    }
    components["total"] = min(100, max(0, sum(components.values())))
    return {key: round(value, 2) for key, value in components.items()}


def score_prominence(
    *,
    sitelinks: int,
    start: int,
    end: int | None,
    has_parent_country: bool = False,  # retained for API compatibility; intentionally ignored
    authoritative: bool = False,
    editorial: bool = False,
    entity_type: str = "polity",
    **kwargs: object,
) -> float:
    del has_parent_country, entity_type
    return prominence_components(
        sitelinks=sitelinks,
        start=start,
        end=end,
        authority_coverage=20 if authoritative else 0,
        editorial_score=7 if editorial else 0,
        **kwargs,
    )["total"]


def tier_for(score: float, override: str | None = None) -> str:
    """Compatibility helper; production tiers are assigned by balanced_visibility()."""
    if override is not None:
        return override
    if score >= 60:
        return "global"
    if score >= 45:
        return "regional"
    return "detailed"


def historical_era(document: dict) -> str:
    end = document.get("end") if document.get("end") is not None else 2026
    midpoint = (int(document["start"]) + int(end)) / 2
    if midpoint < -3000:
        return "early_prehistory"
    if midpoint < 500:
        return "ancient"
    if midpoint < 1500:
        return "medieval"
    if midpoint < 1800:
        return "early_modern"
    if midpoint < 1945:
        return "modern"
    return "contemporary"


def visibility_stratum(document: dict) -> tuple[str, str]:
    geography = document.get("geography") or {}
    continent = geography.get("primary_continent")
    if not continent:
        continent = next(iter(geography.get("continents") or []), "unknown")
    return continent, historical_era(document)


def _top_per_stratum(documents: list[dict], count: int) -> set[str]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for document in documents:
        grouped[visibility_stratum(document)].append(document)
    selected = set()
    for items in grouped.values():
        items.sort(key=lambda item: (-item["prominence_score"], item["canonical_name"], item["id"]))
        selected.update(item["id"] for item in items[:count])
    return selected


def balanced_visibility(documents: list[dict]) -> dict[str, int]:
    normal = [
        document
        for document in documents
        if document.get("entity_type", "polity") in NORMAL_TYPES
        and document.get("eligibility") == "accepted"
        and document.get("entity_type_confidence", "low") != "low"
        and not document.get("prominence_components", {}).get("aggregate_penalty")
    ]
    ranked = sorted(normal, key=lambda item: (-item["prominence_score"], item["canonical_name"], item["id"]))
    global_ids = {item["id"] for item in ranked[:GLOBAL_ABSOLUTE_COUNT]}
    global_ids.update(_top_per_stratum(normal, GLOBAL_PER_STRATUM))
    regional_ids = set(global_ids)
    regional_ids.update(item["id"] for item in ranked[:REGIONAL_ABSOLUTE_COUNT])
    regional_ids.update(_top_per_stratum(normal, REGIONAL_PER_STRATUM))

    counts = {"global": 0, "regional": 0, "detailed": 0}
    for document in documents:
        override = document.get("visibility_override")
        entity_type = document.get("entity_type", "polity")
        if override:
            tier = override
        elif document.get("eligibility") != "accepted" or document.get("entity_type_confidence", "low") == "low":
            tier = "detailed"
        elif entity_type in CONTEXT_TYPES:
            tier = "regional" if document["prominence_score"] >= 45 else "detailed"
        elif document["id"] in global_ids:
            tier = "global"
        elif document["id"] in regional_ids:
            tier = "regional"
        else:
            tier = "detailed"
        document["visibility_tier"] = tier
        counts[tier] += 1
    return counts


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


def compute(polities_dir: Path = POLITIES_DIR, cache_path: Path = CACHE_PATH, offline: bool = False) -> dict[str, int]:
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
    direct_types = json.loads(TYPE_CACHE_PATH.read_text(encoding="utf-8")) if TYPE_CACHE_PATH.exists() else {}
    transitions = yaml.safe_load(TRANSITIONS_PATH.read_text(encoding="utf-8")) if TRANSITIONS_PATH.exists() else []
    transition_counts: defaultdict[str, int] = defaultdict(int)
    for transition in transitions or []:
        for entity_id in set((transition.get("from") or []) + (transition.get("to") or [])):
            transition_counts[entity_id] += 1
    inbound: defaultdict[str, int] = defaultdict(int)
    for document in documents:
        for relationship in document.get("relationships") or []:
            inbound[relationship["target"]] += 1

    for document in documents:
        qid = (document.get("external_ids") or {}).get("wikidata")
        sources = set(document.get("sources") or [])
        authority = (12 if "seshat" in sources else 0) + (4 if "hyde" in sources else 0) + (4 if "maddison" in sources else 0)
        evidence = 20 if document.get("weight_by_era") and not document.get("weight_imputed", True) else 8 if {"hyde", "maddison"} & sources else 0
        text = document.get("text") or {}
        editorial = (5 if text.get("short_adult_en") or text.get("long_en") else 0) + (2 if document.get("icon") else 0)
        degree = len(document.get("relationships") or []) + inbound[document["id"]]
        aggregate = "Q133250" in set((direct_types.get(qid) or {}).get("types", []))
        components = prominence_components(
            sitelinks=sitelinks.get(qid, 0),
            start=document["start"],
            end=document.get("end"),
            authority_coverage=authority,
            historical_evidence=evidence,
            relationship_degree=degree,
            transition_count=transition_counts[document["id"]],
            editorial_score=editorial,
            entity_type_confidence=document.get("entity_type_confidence", "low"),
            start_confidence=document.get("start_confidence", "low"),
            end_confidence=document.get("end_confidence", "low"),
            aggregate=aggregate,
        )
        document["prominence_components"] = components
        document["prominence_score"] = components["total"]

    counts = balanced_visibility(documents)
    for path, document in zip(paths, documents, strict=True):
        path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
    REPORT_PATH.write_text(
        "# Prominence and visibility\n\n"
        + "\n".join(f"- {name.title()}: {count:,}" for name, count in counts.items())
        + f"\n- Global absolute shortlist: {GLOBAL_ABSOLUTE_COUNT}\n"
        + f"- Global per continent/era: {GLOBAL_PER_STRATUM}\n"
        + f"- Regional absolute shortlist: {REGIONAL_ABSOLUTE_COUNT}\n"
        + f"- Regional per continent/era: {REGIONAL_PER_STRATUM}\n",
        encoding="utf-8",
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Require and use the existing sitelink cache")
    args = parser.parse_args()
    counts = compute(offline=args.offline)
    print("Visibility tiers: " + ", ".join(f"{name}={count}" for name, count in counts.items()))


if __name__ == "__main__":
    main()
