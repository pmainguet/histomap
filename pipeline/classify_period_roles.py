"""Route period-like Wikidata records and write the mixed-role editorial queue."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from pipeline.backfill_entity_types import TYPE_QIDS, effective_direct_types

ROOT = Path(__file__).resolve().parents[1]
POLITIES_DIR = ROOT / "polities"
PERIODS_DIR = ROOT / "periods"
DIRECT_TYPES_PATH = ROOT / "sources" / "wikidata_direct_types.json"
ANCESTRY_PATH = ROOT / "sources" / "wikidata_type_ancestors.json"
REPORT_PATH = ROOT / "reports" / "period_role_review.jsonl"
SUMMARY_PATH = ROOT / "reports" / "period_role_summary.md"
PERIOD_ROOTS = {"historical": "Q11514315", "archaeological": "Q15401633"}
ENTITY_ROOTS = set().union(*TYPE_QIDS.values())


def inherited_from(direct_types: set[str], ancestry: dict[str, dict[str, int]], root: str) -> bool:
    return root in direct_types or any(root in ancestry.get(qid, {}) for qid in direct_types)


def period_roles(direct_types: set[str], ancestry: dict[str, dict[str, int]]) -> list[str]:
    return [name for name, root in PERIOD_ROOTS.items() if inherited_from(direct_types, ancestry, root)]


def has_entity_branch(direct_types: set[str], ancestry: dict[str, dict[str, int]]) -> bool:
    return any(inherited_from(direct_types, ancestry, root) for root in ENTITY_ROOTS)


def period_document(document: dict, roles: list[str]) -> dict | None:
    if document.get("end") is None:
        return None
    qid = (document.get("external_ids") or {}).get("wikidata")
    return {
        "id": f"{document['id']}_period",
        "canonical_name": document["canonical_name"],
        "kind": "archaeological" if "archaeological" in roles else "historical",
        "start": document["start"],
        "end": document["end"],
        "start_confidence": document.get("start_confidence", "low"),
        "end_confidence": document.get("end_confidence", "low"),
        "geography": document.get("geography") or {},
        "broader_periods": [],
        "successors": [],
        "authority": "Wikidata period classification",
        "external_ids": {"wikidata": qid} if qid else {},
        "notes": "Period overlay routed from a Wikidata record after editorial role review.",
        "source_urls": [f"https://www.wikidata.org/wiki/{qid}"] if qid else [],
    }


def write_period(document: dict, roles: list[str]) -> str | None:
    value = period_document(document, roles)
    if value is None:
        return None
    PERIODS_DIR.mkdir(exist_ok=True)
    path = PERIODS_DIR / f"{value['id']}.yaml"
    path.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return value["id"]


def run() -> dict[str, int]:
    direct_cache = json.loads(DIRECT_TYPES_PATH.read_text(encoding="utf-8"))
    ancestry = json.loads(ANCESTRY_PATH.read_text(encoding="utf-8")).get("ancestors", {})
    queue = []
    auto_period = 0
    for path in sorted(POLITIES_DIR.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if "timeline_role" in set(document.get("manual_overrides", [])):
            continue
        qid = (document.get("external_ids") or {}).get("wikidata")
        direct_types = effective_direct_types(direct_cache.get(qid) or {})
        roles = period_roles(direct_types, ancestry)
        if not roles:
            continue
        entity_branch = has_entity_branch(direct_types, ancestry)
        if not entity_branch and document.get("end") is not None:
            document["timeline_role"] = "period"
            write_period(document, roles)
            path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
            auto_period += 1
            continue
        queue.append(
            {
                "id": document["id"],
                "canonical_name": document["canonical_name"],
                "wikidata": qid,
                "entity_type": document.get("entity_type", "polity"),
                "period_kinds": roles,
                "direct_type_qids": sorted(direct_types),
                "dates": [document.get("start"), document.get("end")],
                "prominence_score": document.get("prominence_score", 0),
                "reason": "Wikidata classifies this record as both a period and an entity-like subject.",
            }
        )
    queue.sort(key=lambda item: (-float(item["prominence_score"]), item["canonical_name"]))
    REPORT_PATH.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in queue), encoding="utf-8"
    )
    SUMMARY_PATH.write_text(
        f"# Period-role classification\n\n- Mixed records awaiting review: {len(queue):,}\n- Automatically routed period-only records: {auto_period:,}\n",
        encoding="utf-8",
    )
    return {"review": len(queue), "auto_period": auto_period}


if __name__ == "__main__":
    print(run())
