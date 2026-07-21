"""Classify Wikidata candidates using their direct ``instance of`` values.

Broad subclass traversal discovers candidates but also admits cities and other
non-polities. This stage fetches direct P31 claims, applies versioned rules, and
writes an auditable accepted/excluded/review decision report. It does not delete
canonical YAML files.
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 and earlier
    import tomli as tomllib

import pandas as pd
import yaml

try:
    from pipeline.backfill_entity_types import classify_direct_types, effective_direct_types
except ModuleNotFoundError:  # Direct script execution from the repository root.
    from backfill_entity_types import classify_direct_types, effective_direct_types

ROOT = Path(__file__).resolve().parent.parent
PARQUET_PATH = ROOT / "sources" / "wikidata.parquet"
CACHE_PATH = ROOT / "sources" / "wikidata_direct_types.json"
RULES_PATH = ROOT / "pipeline" / "wikidata_types.toml"
REPORT_PATH = ROOT / "reports" / "wikidata_type_decisions.jsonl"
SUMMARY_PATH = ROOT / "reports" / "wikidata_type_summary.md"
POLITIES_DIR = ROOT / "polities"
API_URL = "https://www.wikidata.org/w/api.php"
USER_AGENT = "histomap/0.1 (https://github.com/pmainguet/histomap)"
BATCH_SIZE = 50


@dataclass(frozen=True)
class Decision:
    decision: str
    reason: str


def classify(
    qid: str,
    direct_types: set[str],
    *,
    strong_allow_types: set[str],
    contextual_allow_types: set[str],
    deny_types: set[str],
    review_types: set[str],
    overrides: dict[str, str],
) -> Decision:
    if qid in overrides:
        return Decision(overrides[qid], "explicit QID override")
    strong = sorted(direct_types & strong_allow_types)
    contextual = sorted(direct_types & contextual_allow_types)
    denied = sorted(direct_types & deny_types)
    ambiguous = sorted(direct_types & review_types)
    if strong:
        return Decision("accepted", f"strong direct political type: {', '.join(strong)}")
    if contextual and denied:
        return Decision(
            "review",
            f"mixed contextual political/place types: {', '.join(contextual + denied)}",
        )
    if contextual:
        return Decision("accepted", f"contextual political type: {', '.join(contextual)}")
    if ambiguous:
        return Decision("review", f"ambiguous direct type: {', '.join(ambiguous)}")
    if denied:
        return Decision("excluded", f"direct non-polity type: {', '.join(denied)}")
    return Decision("review", "no direct allow or deny type")


def _fetch_batch(batch: list[str]) -> dict[str, dict]:
    params = urlencode(
        {
            "action": "wbgetentities",
            "format": "json",
            "formatversion": "2",
            "ids": "|".join(batch),
            "props": "claims|labels",
            "languages": "en",
        }
    )
    request = Request(f"{API_URL}?{params}", headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310 - fixed HTTPS endpoint
                entities = json.load(response).get("entities", {})
            result = {}
            for qid in batch:
                entity = entities.get(qid, {})
                claims = []
                for claim in entity.get("claims", {}).get("P31", []):
                    value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                    if isinstance(value, dict) and value.get("id"):
                        claims.append(
                            {"qid": value["id"], "rank": claim.get("rank", "normal")}
                        )
                metadata = {
                    "label": entity.get("labels", {}).get("en", {}).get("value", qid),
                    "claims": claims,
                }
                metadata["types"] = sorted(effective_direct_types(metadata))
                result[qid] = metadata
            return result
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def enrich(qids: list[str], cache_path: Path = CACHE_PATH, offline: bool = False) -> dict[str, dict]:
    cache = (
        json.loads(cache_path.read_text(encoding="utf-8"))
        if cache_path.exists()
        else {}
    )
    absent = set(qids) - set(cache)
    if offline and absent:
        raise ValueError(f"direct-type cache is missing {len(absent)} QIDs")
    # Legacy cache rows contain only a flattened type list. Refresh them online
    # so preferred and deprecated ranks can be applied without breaking offline use.
    legacy = {qid for qid in qids if qid in cache and "claims" not in cache[qid]}
    missing = sorted(absent | (set() if offline else legacy))
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
            print(f"Fetched direct types for {completed}/{len(missing)} remaining QIDs", flush=True)
    return cache


def run(offline: bool = False) -> dict[str, int]:
    frame = pd.read_parquet(PARQUET_PATH)
    qids = frame["qid"].dropna().astype(str).tolist()
    entities = enrich(qids, offline=offline)
    rules = tomllib.loads(RULES_PATH.read_text(encoding="utf-8"))
    strong_allow_types = set(rules["allow"]["strong_qids"])
    contextual_allow_types = set(rules["allow"]["contextual_qids"])
    deny_types = set(rules["deny"]["qids"])
    review_types = set(rules["review"]["qids"])
    overrides = dict(rules.get("overrides", {}))
    rows = []
    counts = {"accepted": 0, "excluded": 0, "review": 0}
    for record in frame.to_dict(orient="records"):
        qid = str(record["qid"])
        entity = entities.get(qid, {"label": record.get("label_en") or qid, "types": []})
        direct_types = effective_direct_types(entity)
        decision = classify(
            qid,
            direct_types,
            strong_allow_types=strong_allow_types,
            contextual_allow_types=contextual_allow_types,
            deny_types=deny_types,
            review_types=review_types,
            overrides=overrides,
        )
        counts[decision.decision] += 1
        entity_type = classify_direct_types(direct_types)
        rows.append(
            {
                "qid": qid,
                "label": entity["label"],
                "direct_types": sorted(direct_types),
                "decision": decision.decision,
                "reason": decision.reason,
                "entity_type": entity_type[0] if entity_type else "polity",
                "entity_type_confidence": entity_type[1] if entity_type else "low",
                "entity_type_source_qids": entity_type[2] if entity_type else [],
                "entity_type_reason": entity_type[3] if entity_type else "no mapped direct type",
            }
        )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    examples = {name: [row for row in rows if row["decision"] == name][:10] for name in counts}
    lines = ["# Wikidata direct-type filter", "", f"Total candidates: {len(rows):,}", ""]
    for name, count in counts.items():
        lines.extend([f"## {name.title()}: {count:,}", ""])
        lines.extend(f"- {row['label']} (`{row['qid']}`): {row['reason']}" for row in examples[name])
        lines.append("")
    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")
    decisions_by_qid = {row["qid"]: row["decision"] for row in rows}
    updated = 0
    for path in POLITIES_DIR.glob("*.yaml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        qid = (document.get("external_ids") or {}).get("wikidata")
        decision = decisions_by_qid.get(qid, "review")
        if document.get("eligibility") != decision:
            document["eligibility"] = decision
            path.write_text(
                yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            updated += 1
    print(f"Updated eligibility on {updated} canonical records")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    counts = run(offline=args.offline)
    print("Type decisions: " + ", ".join(f"{key}={value}" for key, value in counts.items()))


if __name__ == "__main__":
    main()
