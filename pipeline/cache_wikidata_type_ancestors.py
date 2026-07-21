"""Cache Wikidata P279 ancestry for every direct entity type in the candidate set."""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DIRECT_TYPES_PATH = ROOT / "sources" / "wikidata_direct_types.json"
ANCESTRY_PATH = ROOT / "sources" / "wikidata_type_ancestors.json"
API_URL = "https://www.wikidata.org/w/api.php"
USER_AGENT = "histomap/0.1 (https://github.com/pmainguet/histomap)"
BATCH_SIZE = 50
MAX_DEPTH = 8


def effective_parent_qids(claims: list[dict]) -> list[str]:
    """Honor Wikidata rank: preferred replaces normal; deprecated is ignored."""
    usable = [claim for claim in claims if claim.get("rank") != "deprecated"]
    preferred = [claim for claim in usable if claim.get("rank") == "preferred"]
    selected = preferred or [claim for claim in usable if claim.get("rank", "normal") == "normal"]
    values = []
    for claim in selected:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and value.get("id"):
            values.append(value["id"])
    return sorted(set(values))


def _fetch_batch(batch: list[str]) -> dict[str, list[str]]:
    params = urlencode(
        {
            "action": "wbgetentities",
            "format": "json",
            "formatversion": "2",
            "ids": "|".join(batch),
            "props": "claims",
        }
    )
    request = Request(f"{API_URL}?{params}", headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310 - fixed HTTPS endpoint
                entities = json.load(response).get("entities", {})
            return {
                qid: effective_parent_qids(
                    entities.get(qid, {}).get("claims", {}).get("P279", [])
                )
                for qid in batch
            }
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def build(*, refresh: bool = False, max_depth: int = MAX_DEPTH) -> dict[str, dict[str, int]]:
    direct_cache = json.loads(DIRECT_TYPES_PATH.read_text(encoding="utf-8"))
    roots = {
        qid
        for metadata in direct_cache.values()
        for qid in metadata.get("types", [])
    }
    parent_cache: dict[str, list[str]] = {}
    if ANCESTRY_PATH.exists() and not refresh:
        stored = json.loads(ANCESTRY_PATH.read_text(encoding="utf-8"))
        parent_cache = stored.get("parents", {})

    frontier = set(roots)
    visited: set[str] = set()
    for depth in range(max_depth + 1):
        current = sorted(frontier - visited)
        if not current:
            break
        missing = current if refresh else [qid for qid in current if qid not in parent_cache]
        batches = [missing[index : index + BATCH_SIZE] for index in range(0, len(missing), BATCH_SIZE)]
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(_fetch_batch, batch) for batch in batches]
            for future in as_completed(futures):
                parent_cache.update(future.result())
        visited.update(current)
        frontier = {parent for qid in current for parent in parent_cache.get(qid, [])}
        print(f"Ancestry depth {depth}: {len(current)} types; {len(parent_cache)} cached", flush=True)

    ancestry: dict[str, dict[str, int]] = {}
    for root in roots:
        distances: dict[str, int] = {}
        frontier_with_distance = [(root, 0)]
        while frontier_with_distance:
            qid, distance = frontier_with_distance.pop(0)
            if distance >= max_depth:
                continue
            for parent in parent_cache.get(qid, []):
                next_distance = distance + 1
                if next_distance < distances.get(parent, max_depth + 1):
                    distances[parent] = next_distance
                    frontier_with_distance.append((parent, next_distance))
        ancestry[root] = distances
    ANCESTRY_PATH.write_text(
        json.dumps({"max_depth": max_depth, "parents": parent_cache, "ancestors": ancestry}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Cached ancestry for {len(roots)} direct types through {len(parent_cache)} ontology nodes")
    return ancestry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Refetch even already cached ontology nodes")
    parser.add_argument("--max-depth", type=int, default=MAX_DEPTH)
    args = parser.parse_args()
    build(refresh=args.refresh, max_depth=args.max_depth)


if __name__ == "__main__":
    main()
