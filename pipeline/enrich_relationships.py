"""Extract and conservatively apply political relationships from Wikidata.

Only links whose endpoints already exist in the canonical dataset are kept.
Reciprocal statements plus compatible dates can be applied automatically;
one-sided or temporally suspicious links remain in the review report.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import yaml
from SPARQLWrapper import JSON, POST, SPARQLWrapper

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"
CACHE_PATH = ROOT / "sources" / "wikidata_relationships.json"
REPORT_PATH = ROOT / "reports" / "wikidata_relationship_candidates.jsonl"
SUMMARY_PATH = ROOT / "reports" / "wikidata_relationship_summary.md"
GROUPS_PATH = ROOT / "reports" / "display_group_candidates.json"
ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "histomap/0.1 (https://github.com/pmainguet/histomap)"
BATCH_SIZE = 250
MAX_SUCCESSION_GAP = 500
PROPERTIES = ("P131", "P361", "P527", "P155", "P156", "P1365", "P1366", "P17")


@dataclass(frozen=True)
class PolityDates:
    start: int
    end: int | None


def intervals_overlap(left: PolityDates, right: PolityDates) -> bool:
    left_end = left.end if left.end is not None else 2100
    right_end = right.end if right.end is not None else 2100
    return max(left.start, right.start) < min(left_end, right_end)


def succession_dates_compatible(predecessor: PolityDates, successor: PolityDates) -> bool:
    if predecessor.end is None:
        return False
    gap = successor.start - predecessor.end
    return successor.start >= predecessor.start and -25 <= gap <= MAX_SUCCESSION_GAP


def _qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def _property(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def _fetch_batch(qids: list[str]) -> list[dict[str, str]]:
    values = " ".join(f"wd:{qid}" for qid in qids)
    properties = " ".join(f"wdt:{prop}" for prop in PROPERTIES)
    query = f"""
SELECT DISTINCT ?source ?property ?target WHERE {{
  VALUES ?source {{ {values} }}
  VALUES ?property {{ {properties} }}
  ?source ?property ?target .
  FILTER(isIRI(?target))
}}
"""
    sparql = SPARQLWrapper(ENDPOINT, agent=USER_AGENT)
    sparql.setMethod(POST)
    sparql.setReturnFormat(JSON)
    sparql.setQuery(query)
    for attempt in range(3):
        try:
            bindings = sparql.query().convert()["results"]["bindings"]
            return [
                {
                    "source": _qid(row["source"]["value"]),
                    "property": _property(row["property"]["value"]),
                    "target": _qid(row["target"]["value"]),
                }
                for row in bindings
            ]
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def fetch_relationships(qids: list[str], force: bool = False) -> list[dict[str, str]]:
    if CACHE_PATH.exists() and not force:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    rows: list[dict[str, str]] = []
    batches = [qids[index : index + BATCH_SIZE] for index in range(0, len(qids), BATCH_SIZE)]
    completed = 0
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_fetch_batch, batch) for batch in batches]
        for future in as_completed(futures):
            batch_rows = future.result()
            rows.extend(batch_rows)
            completed += BATCH_SIZE
            print(f"Fetched relationships for {min(completed, len(qids))}/{len(qids)} QIDs", flush=True)
    unique = sorted({(row["source"], row["property"], row["target"]) for row in rows})
    result = [dict(zip(("source", "property", "target"), row, strict=True)) for row in unique]
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def assess(
    links: list[dict[str, str]],
    dates: dict[str, PolityDates],
    names: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    names = names or {}
    edges = {(row["source"], row["property"], row["target"]) for row in links}
    candidates: list[dict[str, object]] = []
    for source, prop, target in sorted(edges):
        if source not in dates or target not in dates or source == target:
            continue
        source_name = re.sub(r"\W+", "", names.get(source, source).casefold())
        target_name = re.sub(r"\W+", "", names.get(target, target).casefold())
        possible_duplicate = source_name == target_name
        if prop == "P361":
            reciprocal = (target, "P527", source) in edges
            compatible = intervals_overlap(dates[source], dates[target])
            candidates.append(
                {
                    "kind": "parent",
                    "source": source,
                    "target": target,
                    "properties": ["P361"] + (["P527 reciprocal"] if reciprocal else []),
                    "decision": "auto"
                    if reciprocal and compatible and not possible_duplicate
                    else "review",
                    "reason": "reciprocal and overlapping dates"
                    if reciprocal and compatible and not possible_duplicate
                    else "possible duplicate Wikidata entities with the same name"
                    if possible_duplicate
                    else "one-sided statement or non-overlapping dates",
                }
            )
        elif prop in {"P156", "P1366"}:
            reciprocal_props = {"P156": "P155", "P1366": "P1365"}
            reciprocal = (target, reciprocal_props[prop], source) in edges
            compatible = succession_dates_compatible(dates[source], dates[target])
            candidates.append(
                {
                    "kind": "successor",
                    "source": source,
                    "target": target,
                    "properties": [prop]
                    + ([f"{reciprocal_props[prop]} reciprocal"] if reciprocal else []),
                    "decision": "auto"
                    if reciprocal and compatible and not possible_duplicate
                    else "review",
                    "reason": "reciprocal and chronologically compatible"
                    if reciprocal and compatible and not possible_duplicate
                    else "possible duplicate Wikidata entities with the same name"
                    if possible_duplicate
                    else "one-sided statement or suspicious date gap",
                }
            )
    return candidates


def connected_groups(auto_candidates: list[dict[str, object]], names: dict[str, str]) -> list[dict]:
    graph: dict[str, set[str]] = defaultdict(set)
    for candidate in auto_candidates:
        source = str(candidate["source"])
        target = str(candidate["target"])
        graph[source].add(target)
        graph[target].add(source)
    groups = []
    seen: set[str] = set()
    for node in sorted(graph):
        if node in seen:
            continue
        stack = [node]
        component = []
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            component.append(current)
            stack.extend(graph[current] - seen)
        if len(component) >= 2:
            groups.append(
                {
                    "suggested_name": " / ".join(names[qid] for qid in sorted(component)[:3]),
                    "members": sorted(component),
                    "status": "review",
                }
            )
    return groups


def run(force: bool = False, apply: bool = True) -> dict[str, int]:
    documents: dict[str, tuple[Path, dict]] = {}
    names: dict[str, str] = {}
    dates: dict[str, PolityDates] = {}
    for path in POLITIES_DIR.glob("*.yaml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        qid = (document.get("external_ids") or {}).get("wikidata")
        if not qid or document.get("eligibility") == "excluded":
            continue
        documents[qid] = (path, document)
        names[qid] = document["canonical_name"]
        dates[qid] = PolityDates(document["start"], document.get("end"))

    raw_links = fetch_relationships(sorted(documents), force=force)
    internal_links = [row for row in raw_links if row["source"] in documents and row["target"] in documents]
    candidates = assess(internal_links, dates, names)
    for candidate in candidates:
        candidate["source_name"] = names[str(candidate["source"])]
        candidate["target_name"] = names[str(candidate["target"])]

    auto = [candidate for candidate in candidates if candidate["decision"] == "auto"]
    applied_parent = applied_successor = conflicts = 0
    if apply:
        parents_by_child: dict[str, list[str]] = defaultdict(list)
        successors_by_source: dict[str, list[str]] = defaultdict(list)
        for candidate in auto:
            if candidate["kind"] == "parent":
                parents_by_child[str(candidate["source"])].append(str(candidate["target"]))
            else:
                successors_by_source[str(candidate["source"])].append(str(candidate["target"]))
        changed: set[str] = set()
        for child_qid, parents in parents_by_child.items():
            path, document = documents[child_qid]
            unique = sorted(set(parents))
            if len(unique) == 1 and not document.get("parent"):
                document["parent"] = documents[unique[0]][1]["id"]
                applied_parent += 1
                changed.add(child_qid)
            elif len(unique) > 1:
                conflicts += 1
        for source_qid, successors in successors_by_source.items():
            path, document = documents[source_qid]
            additions = [documents[qid][1]["id"] for qid in sorted(set(successors))]
            before = set(document.get("successors", []))
            document["successors"] = sorted(before | set(additions))
            applied_successor += len(set(document["successors"]) - before)
            if set(document["successors"]) != before:
                changed.add(source_qid)
        for qid in changed:
            path, document = documents[qid]
            path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in candidates), encoding="utf-8"
    )
    groups = connected_groups(auto, names)
    GROUPS_PATH.write_text(json.dumps(groups, indent=2, ensure_ascii=False), encoding="utf-8")
    counts = {
        "raw_links": len(raw_links),
        "internal_links": len(internal_links),
        "auto_candidates": len(auto),
        "review_candidates": len(candidates) - len(auto),
        "parents_applied": applied_parent,
        "successors_applied": applied_successor,
        "conflicts": conflicts,
        "group_candidates": len(groups),
    }
    SUMMARY_PATH.write_text(
        "# Wikidata relationship enrichment\n\n"
        + "\n".join(f"- {key.replace('_', ' ').title()}: {value:,}" for key, value in counts.items())
        + "\n",
        encoding="utf-8",
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Ignore relationship cache")
    parser.add_argument("--no-apply", action="store_true", help="Report without changing YAML")
    args = parser.parse_args()
    counts = run(force=args.force, apply=not args.no_apply)
    print("Relationship enrichment: " + ", ".join(f"{key}={value}" for key, value in counts.items()))


if __name__ == "__main__":
    main()
