"""Classify canonical entities and migrate legacy links to typed relationships."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
POLITIES_DIR = ROOT / "polities"
TYPE_CACHE = ROOT / "sources" / "wikidata_direct_types.json"
ANCESTRY_CACHE = ROOT / "sources" / "wikidata_type_ancestors.json"
COUNTRY_CACHE = ROOT / "sources" / "wikidata_country_metadata.json"
REPORT_PATH = ROOT / "reports" / "entity_type_review.jsonl"
SUMMARY_PATH = ROOT / "reports" / "entity_type_summary.md"

TYPE_QIDS = {
    "polity": {"Q6256", "Q3624078", "Q3024240", "Q48349", "Q417175", "Q1790360", "Q133442", "Q148837", "Q50068795"},
    "civilization": {"Q8432"},
    "subdivision": {"Q56061"},
    "micronation": {"Q188443"},
    "culture": {"Q465299"},
    "people": {"Q41710"},
    "tribe": {"Q133311"},
    "archaeological_horizon": {"Q1636205"},
}
TYPE_PRIORITY = [
    "archaeological_horizon",
    "culture",
    "tribe",
    "people",
    "subdivision",
    "micronation",
    "civilization",
    "polity",
]
CONTEXT_TYPES = {
    "subdivision",
    "micronation",
    "culture",
    "people",
    "tribe",
    "archaeological_horizon",
}


def effective_direct_types(metadata: dict) -> set[str]:
    """Return truthy direct P31 values, respecting Wikidata statement rank."""
    claims = metadata.get("claims")
    if not isinstance(claims, list):
        return set(metadata.get("types", []))
    usable = [claim for claim in claims if claim.get("rank") != "deprecated"]
    preferred = [claim for claim in usable if claim.get("rank") == "preferred"]
    selected = preferred or [claim for claim in usable if claim.get("rank", "normal") == "normal"]
    return {claim["qid"] for claim in selected if claim.get("qid")}


def classify_direct_types(direct_types: set[str]) -> tuple[str, str, list[str], str] | None:
    matches = {
        name: sorted(direct_types & qids)
        for name, qids in TYPE_QIDS.items()
        if direct_types & qids
    }
    if len(matches) == 1:
        entity_type = next(iter(matches))
        return entity_type, "high", matches[entity_type], "direct Wikidata P31"
    if matches:
        entity_type = next(name for name in TYPE_PRIORITY if name in matches)
        source_qids = sorted({item for values in matches.values() for item in values})
        return entity_type, "medium", source_qids, f"conflicting direct types: {', '.join(sorted(matches))}"
    return None


def classify_inherited_types(
    direct_types: set[str], ancestry: dict[str, dict[str, int]]
) -> tuple[str, str, list[str], str] | None:
    """Classify P31 values through their nearest mapped P279 ancestor."""
    matches: dict[str, list[tuple[int, str, str]]] = {}
    for direct_qid in direct_types:
        ancestors = ancestry.get(direct_qid, {})
        for entity_type, roots in TYPE_QIDS.items():
            for root_qid in roots:
                if root_qid in ancestors:
                    matches.setdefault(entity_type, []).append(
                        (int(ancestors[root_qid]), direct_qid, root_qid)
                    )
    if not matches:
        return None
    nearest_distance = min(distance for values in matches.values() for distance, _, _ in values)
    nearest = {
        entity_type: [value for value in values if value[0] == nearest_distance]
        for entity_type, values in matches.items()
        if any(value[0] == nearest_distance for value in values)
    }
    entity_type = next(name for name in TYPE_PRIORITY if name in nearest)
    evidence = nearest[entity_type]
    direct_qids = sorted({direct_qid for _, direct_qid, _ in evidence})
    root_qids = sorted({root_qid for _, _, root_qid in evidence})
    confidence = "medium" if len(nearest) == 1 else "low"
    reason = (
        f"Wikidata P31 subclass path (distance {nearest_distance}) from "
        f"{', '.join(direct_qids)} to {entity_type} root {', '.join(root_qids)}"
    )
    if len(nearest) > 1:
        reason += f"; conflicting nearest types: {', '.join(sorted(nearest))}"
    return entity_type, confidence, direct_qids, reason


def classify_automated_entity(
    document: dict, cached: dict, ancestry: dict[str, dict[str, int]] | None = None
) -> tuple[str, str, list[str], str]:
    qid = (document.get("external_ids") or {}).get("wikidata")
    direct = effective_direct_types(cached.get(qid) or {})
    classified = classify_direct_types(direct)
    inherited = classify_inherited_types(direct, ancestry or {})
    # A generic direct political class (for example historical country) must not
    # hide a more specific civilization/culture branch carried by another P31.
    # Inherited evidence remains reviewable rather than becoming high confidence.
    if classified and classified[0] == "polity" and inherited and inherited[0] in CONTEXT_TYPES | {"civilization"}:
        return inherited
    if classified:
        return classified
    if inherited:
        return inherited
    if (document.get("external_ids") or {}).get("seshat"):
        return "polity", "medium", [], "Seshat record without a mapped direct entity type"
    return "polity", "low", [], "no mapped direct type"


def classify_entity(
    document: dict, cached: dict, ancestry: dict[str, dict[str, int]] | None = None
) -> tuple[str, str, list[str], str]:
    if "entity_type" in set(document.get("manual_overrides", [])):
        return (
            document.get("entity_type", "polity"),
            document.get("entity_type_confidence", "high"),
            document.get("entity_type_source_qids", []),
            "manual override",
        )
    return classify_automated_entity(document, cached, ancestry)


def relationship_kind(source_type: str, target_type: str, legacy_kind: str) -> str:
    if legacy_kind == "parent" and source_type == "subdivision" and target_type == "polity":
        return "administrative_part_of"
    if source_type == target_type == "polity":
        return "political_parent" if legacy_kind == "parent" else "political_successor"
    if legacy_kind == "successor":
        if source_type in {"culture", "archaeological_horizon"} and target_type in {"culture", "archaeological_horizon"}:
            return "archaeological_sequence"
        return "cultural_sequence"
    if target_type == "civilization":
        return "part_of_civilization"
    if target_type in {"people", "tribe"}:
        return "associated_people"
    return "cultural_component"


def normalized_relationship_kind(source_type: str, target_type: str, current_kind: str) -> str:
    """Keep relationship semantics while making its kind valid for new endpoint types."""
    sequence_kinds = {"political_successor", "cultural_sequence", "archaeological_sequence"}
    legacy_kind = "successor" if current_kind in sequence_kinds else "parent"
    expected = relationship_kind(source_type, target_type, legacy_kind)
    if current_kind == "associated_people" and target_type in {"people", "tribe"}:
        return current_kind
    if current_kind == "administrative_part_of" and source_type == "subdivision" and target_type == "polity":
        return current_kind
    if current_kind == "part_of_civilization" and target_type == "civilization":
        return current_kind
    if current_kind == "archaeological_sequence" and source_type in {"culture", "archaeological_horizon"} and target_type in {"culture", "archaeological_horizon"}:
        return current_kind
    if current_kind.startswith("political_") and source_type == target_type == "polity":
        return current_kind
    if current_kind == "cultural_sequence" and not (source_type == target_type == "polity"):
        return current_kind
    if current_kind == "cultural_component":
        return current_kind
    return expected


def run() -> dict[str, int]:
    cache = json.loads(TYPE_CACHE.read_text(encoding="utf-8")) if TYPE_CACHE.exists() else {}
    ancestry_payload = json.loads(ANCESTRY_CACHE.read_text(encoding="utf-8")) if ANCESTRY_CACHE.exists() else {}
    ancestry = ancestry_payload.get("ancestors", {})
    documents = []
    review_rows = []
    counts: Counter[str] = Counter()
    for path in sorted(POLITIES_DIR.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        inferred_type, inferred_confidence, inferred_qids, inferred_reason = (
            classify_automated_entity(document, cache, ancestry)
        )
        reviewed_against = set(document.get("entity_type_reviewed_against", []))
        manual_type = "entity_type" in set(document.get("manual_overrides", []))
        pending_subdivision = (
            inferred_type == "subdivision"
            and "subdivision" not in reviewed_against
            and not (document.get("entity_type") == "subdivision" and document.get("parent"))
        )
        if pending_subdivision:
            entity_type = document.get("entity_type", "polity")
            confidence = document.get("entity_type_confidence", "low")
            source_qids = document.get("entity_type_source_qids", [])
            reason = "existing classification retained until a parent polity is confirmed"
        else:
            entity_type, confidence, source_qids, reason = classify_entity(
                document, cache, ancestry
            )
        document["entity_type"] = entity_type
        document["entity_type_confidence"] = confidence
        document["entity_type_source_qids"] = source_qids
        documents.append((path, document))
        counts[entity_type] += 1
        reconsider_subdivision = pending_subdivision and manual_type and entity_type == "polity"
        if confidence != "high" or pending_subdivision:
            review_rows.append(
                {
                    "id": document["id"],
                    "canonical_name": document["canonical_name"],
                    "wikidata": (document.get("external_ids") or {}).get("wikidata"),
                    "proposed_type": inferred_type if pending_subdivision else entity_type,
                    "confidence": inferred_confidence if pending_subdivision else confidence,
                    "source_qids": inferred_qids if pending_subdivision else source_qids,
                    "reason": (
                        "Previously reviewed as polity; reconsider now that subdivision is "
                        f"available. {inferred_reason}"
                        if reconsider_subdivision
                        else (
                            f"Subdivision requires an enclosing polity. {inferred_reason}"
                            if pending_subdivision
                            else reason
                        )
                    ),
                    "reconsideration": reconsider_subdivision,
                    "requires_parent_review": pending_subdivision,
                }
            )

    by_id = {document["id"]: document for _, document in documents}
    country_metadata = (
        json.loads(COUNTRY_CACHE.read_text(encoding="utf-8")) if COUNTRY_CACHE.exists() else {}
    )
    parent_by_country = {}
    for _, document in documents:
        qid = (document.get("external_ids") or {}).get("wikidata")
        iso2 = (country_metadata.get(qid) or {}).get("iso2")
        if iso2 and document.get("entity_type") == "polity" and document.get("end") is None:
            parent_by_country[iso2] = document["id"]
    for row in review_rows:
        if row["proposed_type"] != "subdivision":
            continue
        document = by_id[row["id"]]
        countries = (document.get("geography") or {}).get("present_countries", [])
        if len(countries) == 1:
            proposed_parent = parent_by_country.get(countries[0])
            if proposed_parent and proposed_parent != row["id"]:
                row["proposed_parent"] = proposed_parent
    migrated = 0
    for path, document in documents:
        source_type = document["entity_type"]
        relationships = []
        for item in document.get("relationships") or []:
            target = by_id.get(item["target"])
            if target is None:
                relationships.append(item)
                continue
            item = dict(item)
            item["kind"] = normalized_relationship_kind(
                source_type, target["entity_type"], item["kind"]
            )
            if not any(
                existing["kind"] == item["kind"] and existing["target"] == item["target"]
                for existing in relationships
            ):
                relationships.append(item)
        existing = {(item["kind"], item["target"]) for item in relationships}
        parent = document.get("parent")
        legacy = ([('parent', parent)] if parent else []) + [
            ("successor", target) for target in document.get("successors", [])
        ]
        for legacy_kind, target_id in legacy:
            target = by_id.get(target_id)
            if target is None:
                continue
            kind = relationship_kind(source_type, target["entity_type"], legacy_kind)
            if (kind, target_id) not in existing:
                relationships.append(
                    {
                        "target": target_id,
                        "kind": kind,
                        "evidence": "derived",
                        "confidence": "medium",
                        "source_urls": [
                            f"https://www.wikidata.org/wiki/{document['external_ids']['wikidata']}"
                        ] if (document.get("external_ids") or {}).get("wikidata") else [],
                    }
                )
                existing.add((kind, target_id))
                migrated += 1
        document["relationships"] = relationships
        if source_type in CONTEXT_TYPES:
            document["weight_by_era"] = {int(document["start"]): 3}
            document["weight_imputed"] = True
            document["sources"] = sorted(
                set(document.get("sources", [])) - {"hyde", "maddison"}
            )
        if source_type not in {"polity", "subdivision"} or (
            parent and by_id.get(parent, {}).get("entity_type") != "polity"
        ):
            document["parent"] = None
        document["successors"] = [
            target for target in document.get("successors", [])
            if source_type == "polity" and by_id.get(target, {}).get("entity_type") == "polity"
        ]
        path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")

    relationship_total = sum(
        len(document.get("relationships") or []) for _, document in documents
    )

    REPORT_PATH.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in review_rows), encoding="utf-8"
    )
    SUMMARY_PATH.write_text(
        "# Entity type backfill\n\n"
        + "\n".join(f"- {name.replace('_', ' ').title()}: {count:,}" for name, count in sorted(counts.items()))
        + f"\n- Review queue: {len(review_rows):,}\n- Typed relationships: {relationship_total:,}"
        + f"\n- Newly migrated relationships: {migrated:,}\n",
        encoding="utf-8",
    )
    return {**counts, "review": len(review_rows), "relationships": relationship_total}


if __name__ == "__main__":
    result = run()
    print("Entity types: " + ", ".join(f"{key}={value}" for key, value in sorted(result.items())))
