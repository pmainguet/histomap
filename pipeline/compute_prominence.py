"""Compute display prominence without deleting canonical polity records.

Wikidata sitelink counts provide a language-diverse proxy for public/historical
reach. Longevity, authoritative-source coverage, editorial work, and a penalty
for entities assigned to another country refine that signal. The score controls
only default visibility; every record remains available in the detailed view.
"""

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

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"
PARQUET_PATH = ROOT / "sources" / "wikidata.parquet"
CACHE_PATH = ROOT / "sources" / "wikidata_sitelinks.json"
API_URL = "https://www.wikidata.org/w/api.php"
USER_AGENT = "histomap/0.1 (https://github.com/pmainguet/histomap)"
BATCH_SIZE = 50
GLOBAL_THRESHOLD = 55
REGIONAL_THRESHOLD = 45


def score_prominence(
    *,
    sitelinks: int,
    start: int,
    end: int | None,
    has_parent_country: bool,
    authoritative: bool,
    editorial: bool,
    current_year: int = 2026,
) -> float:
    duration = max(1, (end if end is not None else current_year) - start)
    reach = 25 * math.log10(1 + max(0, sitelinks))
    longevity = min(12, 4 * math.log10(1 + duration))
    authority_bonus = 12 if authoritative else 0
    editorial_bonus = 8 if editorial else 0
    subordinate_penalty = 18 if has_parent_country else 0
    return round(min(100, max(0, reach + longevity + authority_bonus + editorial_bonus - subordinate_penalty)), 2)


def tier_for(score: float, override: str | None = None) -> str:
    if override is not None:
        return override
    if score >= GLOBAL_THRESHOLD:
        return "global"
    if score >= REGIONAL_THRESHOLD:
        return "regional"
    return "detailed"


def _load_cache(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    return {str(qid): int(count) for qid, count in json.loads(path.read_text(encoding="utf-8")).items()}


def _fetch_batch(batch: list[str]) -> dict[str, int]:
    params = urlencode(
        {
            "action": "wbgetentities",
            "format": "json",
            "formatversion": "2",
            "ids": "|".join(batch),
            "props": "sitelinks",
        }
    )
    request = Request(f"{API_URL}?{params}", headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310 - fixed HTTPS endpoint
                payload = json.load(response)
            entities = payload.get("entities", {})
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
    completed = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_fetch_batch, batch) for batch in batches]
        for future in as_completed(futures):
            result = future.result()
            cache.update(result)
            completed += len(result)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
            print(f"Fetched sitelinks for {completed}/{len(missing)} remaining QIDs", flush=True)
    return cache


def compute(
    polities_dir: Path = POLITIES_DIR,
    parquet_path: Path = PARQUET_PATH,
    cache_path: Path = CACHE_PATH,
    offline: bool = False,
) -> dict[str, int]:
    frame = pd.read_parquet(parquet_path, columns=["qid", "country_qid"])
    country_by_qid = dict(zip(frame["qid"], frame["country_qid"], strict=True))
    paths = sorted(polities_dir.glob("*.yaml"))
    documents = [(path, yaml.safe_load(path.read_text(encoding="utf-8"))) for path in paths]
    qids = [
        document.get("external_ids", {}).get("wikidata")
        for _, document in documents
        if document.get("external_ids", {}).get("wikidata")
    ]
    sitelinks = _load_cache(cache_path) if offline else fetch_sitelinks(qids, cache_path)
    if offline and set(qids) - set(sitelinks):
        raise ValueError("sitelink cache is incomplete; rerun without --offline")

    counts = {"global": 0, "regional": 0, "detailed": 0}
    for path, document in documents:
        qid = document.get("external_ids", {}).get("wikidata")
        text = document.get("text") or {}
        score = score_prominence(
            sitelinks=sitelinks.get(qid, 0),
            start=document["start"],
            end=document.get("end"),
            # For extinct polities P17 often means present-day location, not
            # subordination (for example an ancient empire located in modern Iran).
            has_parent_country=bool(country_by_qid.get(qid)) and document.get("end") is None
            if qid
            else False,
            authoritative="seshat" in document.get("sources", []),
            editorial=bool(document.get("icon") or text.get("short_adult_en")),
        )
        tier = tier_for(score, document.get("visibility_override"))
        document["prominence_score"] = score
        document["visibility_tier"] = tier
        path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
        counts[tier] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Require and use the existing sitelink cache")
    args = parser.parse_args()
    counts = compute(offline=args.offline)
    print("Visibility tiers: " + ", ".join(f"{name}={count}" for name, count in counts.items()))


if __name__ == "__main__":
    main()
