"""Serve Histomap pages and a constrained local review/pipeline API."""

from __future__ import annotations

import asyncio
import json
import math
import re
import sys
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import yaml

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from rapidfuzz import fuzz

from pipeline.review_cli import pending_records, polity_metadata, save_decision
from pipeline.backfill_entity_types import normalized_relationship_kind, relationship_kind
from schema import Geography

ROOT = Path(__file__).resolve().parent.parent
ALLOWED_ACTIONS = {
    "apply-reviews": ["-m", "pipeline.apply_review_decisions"],
    "reconcile": ["pipeline/reconcile.py"],
    "build": ["-m", "pipeline.rebuild_timeline"],
    "compute-weights": ["pipeline/compute_weights.py"],
}
EQUINOX_URL = (
    "https://github.com/seshatdb/Equinox_Data/blob/master/"
    "Equinox_on_GitHub_June9_2022.xlsx"
)
CONTINENTS = ["africa", "asia", "europe", "north_america", "south_america", "oceania", "antarctica"]
ENTITY_TYPE_REVIEW_ORDER = {
    "civilization": 0,
    "polity": 1,
    "subdivision": 2,
    "micronation": 3,
    "culture": 4,
    "people": 5,
    "tribe": 6,
    "archaeological_horizon": 7,
}


def entity_type_review_sort_key(item: dict) -> tuple:
    """Group reviews by proposed type, then put stronger/high-value cases first."""
    return (
        ENTITY_TYPE_REVIEW_ORDER.get(item.get("proposed_type"), len(ENTITY_TYPE_REVIEW_ORDER)),
        0 if item.get("reconsideration") else 1,
        0 if item.get("confidence") == "medium" else 1,
        -float(item.get("prominence_score", 0)),
        item.get("canonical_name", ""),
    )


def english_wikipedia_url(external_ids: dict) -> str | None:
    if external_ids.get("wikipedia_en"):
        return str(external_ids["wikipedia_en"])
    if external_ids.get("wikidata"):
        return (
            "https://www.wikidata.org/wiki/Special:GoToLinkedPage/"
            f"enwiki/{external_ids['wikidata']}"
        )
    return None


class ReviewDecision(BaseModel):
    decision: Literal["accept", "reject", "defer"]
    polity_id: str | None = None


class GeographyUpdate(BaseModel):
    continents: list[str]
    primary_continent: str | None = None
    present_countries: list[str]


class EntityTypeUpdate(BaseModel):
    entity_type: Literal[
        "polity",
        "civilization",
        "subdivision",
        "micronation",
        "culture",
        "people",
        "tribe",
        "archaeological_horizon",
    ]


class SubdivisionParentUpdate(BaseModel):
    parent_id: str


class TimelineRoleUpdate(BaseModel):
    timeline_role: Literal["entity", "period", "both"]


class ConsolidationDecision(BaseModel):
    decision: Literal["independent", "same_entity", "phase_of"]
    target_id: str | None = None


def clean_json(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: clean_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_json(item) for item in value]
    return value


def add_source_links(record: dict, metadata: dict[str, dict]) -> dict:
    enriched = dict(record)
    source_name = record.get("seshat_long_name") or record["seshat_name"]
    enriched["source_links"] = [
        {
            "label": "Seshat polity search",
            "url": "https://www.seshat-db.com/api/core/polities/?search="
            + quote(str(source_name)),
        },
        {"label": "Equinox 2020 workbook", "url": EQUINOX_URL},
        {
            "label": "Google search",
            "url": "https://www.google.com/search?q=" + quote(str(source_name)),
        },
    ]
    enriched_candidates = []
    for candidate in record.get("candidates", []):
        enriched_candidate = dict(candidate)
        document = metadata.get(candidate["polity_id"], {})
        external_ids = document.get("external_ids") or {}
        enriched_candidate["canonical_start"] = document.get("start")
        enriched_candidate["canonical_end"] = document.get("end")
        enriched_candidate["canonical_sources"] = document.get("sources", [])
        enriched_candidate["external_ids"] = external_ids
        links = []
        if external_ids.get("wikidata"):
            links.append(
                {
                    "label": "Wikidata",
                    "url": f"https://www.wikidata.org/wiki/{external_ids['wikidata']}",
                }
            )
        wikipedia_url = english_wikipedia_url(external_ids)
        if wikipedia_url:
            links.append({"label": "Wikipedia (English)", "url": wikipedia_url})
        if external_ids.get("seshat"):
            links.append(
                {
                    "label": "Seshat polity search",
                    "url": "https://www.seshat-db.com/api/core/polities/?search="
                    + quote(str(document.get("canonical_name", candidate["canonical_name"]))),
                }
            )
        comparison_query = f"{candidate['canonical_name']} vs {source_name}"
        links.append(
            {
                "label": "Google comparison",
                "url": "https://www.google.com/search?q=" + quote(comparison_query),
            }
        )
        enriched_candidate["source_links"] = links
        enriched_candidates.append(enriched_candidate)
    enriched["candidates"] = enriched_candidates
    return enriched


def search_polities(query: str, metadata: dict[str, dict], limit: int = 10) -> list[dict]:
    query = query.strip()
    ranked = []
    for polity_id, document in metadata.items():
        if document.get("eligibility") == "excluded" or document.get("timeline_role") == "retired":
            continue
        names = [str(document.get("canonical_name", "")), polity_id]
        for key, value in (document.get("names") or {}).items():
            if key == "aliases_en":
                names.extend(part.strip() for part in str(value).split("|") if part.strip())
            elif value:
                names.append(str(value))
        score = max(float(fuzz.WRatio(query, name)) for name in names if name)
        exact_alias = any(query.casefold() == name.casefold() for name in names if name)
        ranked.append((not exact_alias, -score, str(document.get("canonical_name", "")), polity_id))
    results = []
    for _, negative_score, _, polity_id in sorted(ranked)[:limit]:
        document = metadata[polity_id]
        external_ids = document.get("external_ids") or {}
        links = []
        if external_ids.get("wikidata"):
            links.append({"label": "Wikidata", "url": f"https://www.wikidata.org/wiki/{external_ids['wikidata']}"})
        wikipedia_url = english_wikipedia_url(external_ids)
        if wikipedia_url:
            links.append({"label": "Wikipedia (English)", "url": wikipedia_url})
        results.append(
            {
                "polity_id": polity_id,
                "canonical_name": document.get("canonical_name", polity_id),
                "entity_type": document.get("entity_type", "polity"),
                "canonical_start": document.get("start"),
                "canonical_end": document.get("end"),
                "canonical_sources": document.get("sources", []),
                "source_links": links,
                "search_score": round(-negative_score, 1),
            }
        )
    return results


def create_app(root: Path = ROOT) -> FastAPI:
    application = FastAPI(title="Histomap", version="0.1.0")
    web_dir = root / "web"
    reports_dir = root / "reports"
    review_path = reports_dir / "seshat_reconciliation.jsonl"
    decisions_path = reports_dir / "seshat_review_decisions.jsonl"
    type_review_path = reports_dir / "entity_type_review.jsonl"
    period_role_review_path = reports_dir / "period_role_review.jsonl"
    relationship_cache_path = root / "sources" / "wikidata_relationships.json"
    direct_types_path = root / "sources" / "wikidata_direct_types.json"
    polities_dir = root / "polities"
    metadata = polity_metadata(polities_dir)
    country_metadata_path = root / "sources" / "wikidata_country_metadata.json"
    country_metadata = (
        json.loads(country_metadata_path.read_text(encoding="utf-8"))
        if country_metadata_path.exists()
        else {}
    )
    country_options = {
        info["iso2"]: info.get("label", info["iso2"])
        for info in country_metadata.values()
        if info.get("iso2") and len(info["iso2"]) == 2
    }
    relationship_rows = (
        json.loads(relationship_cache_path.read_text(encoding="utf-8"))
        if relationship_cache_path.exists()
        else []
    )
    direct_types = (
        json.loads(direct_types_path.read_text(encoding="utf-8"))
        if direct_types_path.exists()
        else {}
    )
    review_queue = pending_records(review_path, decisions_path, metadata=metadata)
    reviews_by_id = {record["seshat_id"]: record for record in review_queue}
    type_review_queue = []

    def refresh_type_review_queue() -> None:
        type_review_queue.clear()
        if type_review_path.exists():
            for line in type_review_path.read_text(encoding="utf-8").splitlines():
                record = json.loads(line)
                document = metadata.get(record["id"])
                reviewed_types = set(document.get("entity_type_reviewed_against", [])) if document else set()
                proposal_already_reviewed = record.get("proposed_type") in reviewed_types
                if document and document.get("timeline_role", "entity") != "retired" and (
                    document.get("entity_type_confidence", "low") != "high"
                    or (
                        (record.get("reconsideration") or record.get("requires_parent_review"))
                        and not proposal_already_reviewed
                    )
                ):
                    record["prominence_score"] = document.get("prominence_score", 0)
                    record["dates"] = [document.get("start"), document.get("end")]
                    record["sources"] = document.get("sources", [])
                    record["wikipedia_en"] = (document.get("external_ids") or {}).get("wikipedia_en")
                    wikidata_qid = (document.get("external_ids") or {}).get("wikidata")
                    record["direct_type_qids"] = sorted(
                        set((direct_types.get(wikidata_qid) or {}).get("types", []))
                    )
                    type_review_queue.append(record)
        type_review_queue.sort(key=entity_type_review_sort_key)

    refresh_type_review_queue()
    period_role_queue: list[dict] = []

    def refresh_period_role_queue() -> None:
        period_role_queue.clear()
        if not period_role_review_path.exists():
            return
        for line in period_role_review_path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            document = metadata.get(record["id"])
            if document and document.get("timeline_role", "entity") != "retired" and "timeline_role" not in set(document.get("manual_overrides", [])):
                record["wikipedia_en"] = english_wikipedia_url(document.get("external_ids") or {})
                period_role_queue.append(record)

    refresh_period_role_queue()
    job = {"status": "idle", "action": None, "output": "", "returncode": None}
    job_lock = asyncio.Lock()

    def refresh_review_queue() -> None:
        metadata.clear()
        metadata.update(polity_metadata(polities_dir))
        review_queue.clear()
        review_queue.extend(pending_records(review_path, decisions_path, metadata=metadata))
        reviews_by_id.clear()
        reviews_by_id.update((record["seshat_id"], record) for record in review_queue)

    def refresh_separate_entities() -> None:
        for path in polities_dir.glob("seshat_*.yaml"):
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            metadata[document["id"]] = document

    def subdivision_parent_candidates(document: dict) -> list[dict]:
        qid_to_id = {
            (item.get("external_ids") or {}).get("wikidata"): item_id
            for item_id, item in metadata.items()
            if (item.get("external_ids") or {}).get("wikidata")
        }
        source_qid = (document.get("external_ids") or {}).get("wikidata")
        scores: dict[str, dict] = {}

        def add(parent_id: str | None, score: int, evidence: str) -> None:
            parent = metadata.get(parent_id or "")
            if not parent or parent.get("entity_type", "polity") != "polity":
                return
            candidate = scores.setdefault(
                parent_id,
                {
                    "id": parent_id,
                    "canonical_name": parent.get("canonical_name", parent_id),
                    "wikidata": (parent.get("external_ids") or {}).get("wikidata"),
                    "score": 0,
                    "evidence": [],
                },
            )
            candidate["score"] += score
            if evidence not in candidate["evidence"]:
                candidate["evidence"].append(evidence)

        property_scores = {"P131": 100, "P361": 80, "P17": 60}
        frontier = [(source_qid, [], 0)] if source_qid else []
        visited = {source_qid}
        while frontier:
            current_qid, path_evidence, depth = frontier.pop(0)
            if depth >= 3:
                continue
            for row in relationship_rows:
                if row.get("source") != current_qid or row.get("property") not in property_scores:
                    continue
                prop = row["property"]
                target_qid = row.get("target")
                evidence = [*path_evidence, f"Wikidata {prop} → {target_qid}"]
                target_id = qid_to_id.get(target_qid)
                add(target_id, max(10, property_scores[prop] - depth * 20), " · ".join(evidence))
                if target_qid not in visited:
                    visited.add(target_qid)
                    frontier.append((target_qid, evidence, depth + 1))

        countries = (document.get("geography") or {}).get("present_countries", [])
        if len(countries) == 1:
            iso2 = countries[0]
            for qid, info in country_metadata.items():
                if info.get("iso2") == iso2:
                    add(qid_to_id.get(qid), 40, f"Present-country geography → {iso2}")
        if document.get("parent"):
            add(document["parent"], 150, "Existing canonical parent")
        return sorted(
            scores.values(),
            key=lambda item: (-item["score"], item["canonical_name"], item["id"]),
        )

    def subdivision_review_queue() -> list[dict]:
        queue = []
        for document in metadata.values():
            if document.get("timeline_role", "entity") == "retired":
                continue
            if document.get("entity_type") != "subdivision":
                continue
            if document.get("subdivision_parent_status", "pending") == "confirmed":
                continue
            queue.append(
                {
                    "id": document["id"],
                    "canonical_name": document["canonical_name"],
                    "wikidata": (document.get("external_ids") or {}).get("wikidata"),
                    "dates": [document.get("start"), document.get("end")],
                    "prominence_score": document.get("prominence_score", 0),
                    "candidates": subdivision_parent_candidates(document),
                }
            )
        queue.sort(
            key=lambda item: (
                0 if item["candidates"] else 1,
                -float(item.get("prominence_score", 0)),
                item["canonical_name"],
            )
        )
        return queue

    consolidation_stopwords = {
        "ancient", "caliphate", "confederation", "county", "democratic", "duchy",
        "dynasty", "empire", "federation", "government", "great", "kingdom",
        "northern", "people", "principality", "province", "republic", "southern",
        "state", "sultanate", "united", "western", "eastern",
        "califat", "comte", "duche", "dynastie", "etat", "gouvernement", "publique",
        "royaume", "sultanat",
    }

    def consolidation_tokens(document: dict) -> set[str]:
        names = [document.get("canonical_name", "")]
        names.extend((document.get("names") or {}).values())
        return {
            token
            for name in names
            for token in re.findall(r"[a-z0-9]+", str(name).casefold())
            if len(token) >= 4 and token not in consolidation_stopwords
        }

    def consolidation_review_queue() -> list[dict]:
        active = {
            entity_id: document
            for entity_id, document in metadata.items()
            if document.get("timeline_role", "entity") != "retired"
            and document.get("eligibility") != "excluded"
            and not document.get("consolidation_status")
        }
        token_index: dict[str, set[str]] = {}
        tokens_by_id = {}
        for entity_id, document in active.items():
            tokens = consolidation_tokens(document)
            tokens_by_id[entity_id] = tokens
            for token in tokens:
                token_index.setdefault(token, set()).add(entity_id)
        queue = []
        for entity_id, document in active.items():
            possible = {
                other_id
                for token in tokens_by_id[entity_id]
                if len(token_index[token]) <= 12
                for other_id in token_index[token]
                if other_id != entity_id
            }
            candidates = []
            source_name = str(document.get("canonical_name", entity_id))
            source_prominence = float(document.get("prominence_score", 0))
            source_countries = set((document.get("geography") or {}).get("present_countries", []))
            for other_id in possible:
                other = active[other_id]
                other_prominence = float(other.get("prominence_score", 0))
                if other_prominence < source_prominence:
                    continue
                name_score = float(fuzz.WRatio(source_name, str(other.get("canonical_name", other_id))))
                if name_score < 60:
                    continue
                other_countries = set((other.get("geography") or {}).get("present_countries", []))
                geography_match = bool(source_countries & other_countries)
                date_contains = (
                    other.get("start") is not None
                    and document.get("start") is not None
                    and other["start"] <= document["start"]
                    and (other.get("end") is None or (document.get("end") is not None and other["end"] >= document["end"]))
                )
                source_end = document.get("end") if document.get("end") is not None else 2100
                other_end = other.get("end") if other.get("end") is not None else 2100
                date_overlap = document.get("start") is not None and other.get("start") is not None and max(document["start"], other["start"]) < min(source_end, other_end)
                shared_tokens = tokens_by_id[entity_id] & tokens_by_id[other_id]
                rarity_bonus = max(
                    (max(4, 16 - len(token_index[token])) for token in shared_tokens),
                    default=0,
                )
                score = name_score + rarity_bonus + (8 if geography_match else 0) + (8 if date_contains else 0) + (6 if date_overlap else 0)
                candidates.append(
                    {
                        "id": other_id,
                        "canonical_name": other.get("canonical_name", other_id),
                        "entity_type": other.get("entity_type", "polity"),
                        "dates": [other.get("start"), other.get("end")],
                        "wikidata": (other.get("external_ids") or {}).get("wikidata"),
                        "score": round(score, 1),
                        "name_score": round(name_score, 1),
                        "geography_match": geography_match,
                        "date_contains": date_contains,
                        "date_overlap": date_overlap,
                    }
                )
            candidates.sort(key=lambda item: (-item["score"], item["canonical_name"]))
            if candidates:
                queue.append(
                    {
                        "id": entity_id,
                        "canonical_name": source_name,
                        "entity_type": document.get("entity_type", "polity"),
                        "dates": [document.get("start"), document.get("end")],
                        "wikidata": (document.get("external_ids") or {}).get("wikidata"),
                        "prominence_score": source_prominence,
                        "candidates": candidates[:5],
                    }
                )
        queue.sort(key=lambda item: (-item["candidates"][0]["score"], -item["prominence_score"], item["canonical_name"]))
        return queue

    def save_consolidation(entity_id: str, decision: str, target_id: str | None) -> dict:
        document = metadata.get(entity_id)
        if not document or document.get("timeline_role") == "retired" or document.get("consolidation_status"):
            raise HTTPException(404, "Consolidation review is not pending")
        if decision == "independent":
            document["consolidation_status"] = "independent"
            document["manual_overrides"] = sorted(set(document.get("manual_overrides", [])) | {"consolidation"})
            (polities_dir / f"{entity_id}.yaml").write_text(
                yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            return document
        target = metadata.get(target_id or "")
        if not target or target_id == entity_id or target.get("timeline_role") == "retired":
            raise HTTPException(422, "target_id must identify another active entity")
        if decision == "phase_of" and document.get("end") is None:
            raise HTTPException(422, "A phase/aspect requires a finite end date")

        document["timeline_role"] = "retired"
        document["consolidation_status"] = decision
        document["consolidated_into"] = target_id
        document["manual_overrides"] = sorted(set(document.get("manual_overrides", [])) | {"consolidation"})
        if decision == "same_entity":
            aliases = {
                item.strip()
                for item in str((target.get("names") or {}).get("aliases_en", "")).split("|")
                if item.strip()
            }
            aliases.add(document["canonical_name"])
            target.setdefault("names", {})["aliases_en"] = " | ".join(sorted(aliases))
            target["sources"] = sorted(set(target.get("sources", [])) | set(document.get("sources", [])))
            target["manual_overrides"] = sorted(set(target.get("manual_overrides", [])) | {"consolidation"})
            (polities_dir / f"{target_id}.yaml").write_text(
                yaml.safe_dump(target, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
        else:
            period_id = f"{entity_id}_period"
            qid = (document.get("external_ids") or {}).get("wikidata")
            source_urls = [f"https://www.wikidata.org/wiki/{qid}"] if qid else [f"https://histomap.local/entity/{entity_id}"]
            period = {
                "id": period_id,
                "canonical_name": document["canonical_name"],
                "kind": "historical",
                "start": document["start"],
                "end": document["end"],
                "start_confidence": document.get("start_confidence", "low"),
                "end_confidence": document.get("end_confidence", "low"),
                "geography": document.get("geography") or {},
                "broader_periods": [], "successors": [],
                "authority": "Histomap editorial consolidation",
                "external_ids": {"wikidata": qid} if qid else {},
                "notes": f"Editorially identified as a phase or aspect of {target['canonical_name']}.",
                "source_urls": source_urls,
            }
            periods_dir = root / "periods"
            periods_dir.mkdir(exist_ok=True)
            (periods_dir / f"{period_id}.yaml").write_text(
                yaml.safe_dump(period, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            links_path = root / "period_links.yaml"
            links = yaml.safe_load(links_path.read_text(encoding="utf-8")) if links_path.exists() else []
            if not any(link.get("period_id") == period_id and link.get("entity_id") == target_id for link in links):
                links.append({
                    "period_id": period_id, "entity_id": target_id,
                    "relation": "part_of_periodization", "evidence": "explicit",
                    "confidence": "high", "source_urls": source_urls,
                    "notes": "Created by an editorial entity-consolidation decision.",
                })
                links_path.write_text(yaml.safe_dump(links, sort_keys=False, allow_unicode=True), encoding="utf-8")
        (polities_dir / f"{entity_id}.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        metadata[entity_id] = document
        metadata[target_id] = target
        return document

    def save_entity_type(
        polity_id: str,
        entity_type: str,
        reviewed_against: str | None = None,
    ) -> dict:
        document = metadata.get(polity_id)
        path = polities_dir / f"{polity_id}.yaml"
        if document is None or not path.exists():
            raise HTTPException(404, "Unknown Histomap entity")
        def add_typed_relationship(source: dict, target: dict, legacy_kind: str) -> None:
            kind = relationship_kind(
                source.get("entity_type", "polity"), target.get("entity_type", "polity"), legacy_kind
            )
            relationships = source.setdefault("relationships", [])
            if any(item.get("kind") == kind and item.get("target") == target["id"] for item in relationships):
                return
            qid = (source.get("external_ids") or {}).get("wikidata")
            relationships.append(
                {
                    "target": target["id"],
                    "kind": kind,
                    "evidence": "derived",
                    "confidence": "medium",
                    "source_urls": [f"https://www.wikidata.org/wiki/{qid}"] if qid else [],
                }
            )

        document["entity_type"] = entity_type
        document["entity_type_confidence"] = "high"
        document["entity_type_source_qids"] = []
        document["manual_overrides"] = sorted(
            set(document.get("manual_overrides", [])) | {"entity_type"}
        )
        if reviewed_against:
            document["entity_type_reviewed_against"] = sorted(
                set(document.get("entity_type_reviewed_against", [])) | {reviewed_against}
            )
        if entity_type == "subdivision":
            document["parent"] = None
            document["subdivision_parent_status"] = "pending"
        else:
            document.pop("subdivision_parent_status", None)
        changed = {polity_id}
        if document.get("parent"):
            target = metadata.get(document["parent"])
            if target:
                add_typed_relationship(document, target, "parent")
            if entity_type not in {"polity", "subdivision"} or (
                target and target.get("entity_type", "polity") != "polity"
            ):
                document["parent"] = None
        retained_successors = []
        for target_id in document.get("successors", []):
            target = metadata.get(target_id)
            if target:
                add_typed_relationship(document, target, "successor")
            if entity_type == "polity" and target and target.get("entity_type", "polity") == "polity":
                retained_successors.append(target_id)
        document["successors"] = retained_successors
        for candidate_id, candidate in metadata.items():
            if candidate_id == polity_id:
                continue
            candidate_changed = False
            if candidate.get("parent") == polity_id:
                add_typed_relationship(candidate, document, "parent")
                candidate_changed = True
                if candidate.get("entity_type", "polity") != "polity" or entity_type != "polity":
                    candidate["parent"] = None
                    candidate_changed = True
            if polity_id in (candidate.get("successors") or []):
                add_typed_relationship(candidate, document, "successor")
                candidate_changed = True
                if candidate.get("entity_type", "polity") != "polity" or entity_type != "polity":
                    candidate["successors"] = [item for item in candidate["successors"] if item != polity_id]
                    candidate_changed = True
            if candidate_changed:
                changed.add(candidate_id)
        for changed_id in changed:
            changed_document = metadata[changed_id]
            (polities_dir / f"{changed_id}.yaml").write_text(
                yaml.safe_dump(changed_document, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
        metadata[polity_id] = document
        return document

    def save_subdivision_parent(polity_id: str, parent_id: str) -> dict:
        document = metadata.get(polity_id)
        parent = metadata.get(parent_id)
        if document is None or document.get("entity_type") != "subdivision":
            raise HTTPException(404, "Subdivision review is not pending")
        if document.get("subdivision_parent_status", "pending") == "confirmed":
            raise HTTPException(404, "Subdivision review is not pending")
        if parent is None or parent.get("entity_type", "polity") != "polity":
            raise HTTPException(422, "parent_id must identify a polity")
        if parent_id == polity_id:
            raise HTTPException(422, "A subdivision cannot be its own parent")
        document["parent"] = parent_id
        document["subdivision_parent_status"] = "confirmed"
        document["manual_overrides"] = sorted(
            set(document.get("manual_overrides", [])) | {"subdivision_parent"}
        )
        relationships = []
        for item in document.get("relationships") or []:
            target = metadata.get(item.get("target"))
            if target:
                item = dict(item)
                item["kind"] = normalized_relationship_kind(
                    "subdivision", target.get("entity_type", "polity"), item["kind"]
                )
            if not (
                item.get("kind") == "administrative_part_of"
                and item.get("target") != parent_id
            ):
                relationships.append(item)
        if not any(
            item.get("kind") == "administrative_part_of" and item.get("target") == parent_id
            for item in relationships
        ):
            qid = (document.get("external_ids") or {}).get("wikidata")
            relationships.append(
                {
                    "target": parent_id,
                    "kind": "administrative_part_of",
                    "evidence": "derived",
                    "confidence": "high",
                    "source_urls": [f"https://www.wikidata.org/wiki/{qid}"] if qid else [],
                }
            )
        document["relationships"] = relationships
        path = polities_dir / f"{polity_id}.yaml"
        path.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        metadata[polity_id] = document
        return document

    def save_timeline_role(polity_id: str, timeline_role: str, period_kinds: list[str]) -> dict:
        document = metadata.get(polity_id)
        path = polities_dir / f"{polity_id}.yaml"
        if document is None or not path.exists():
            raise HTTPException(404, "Unknown Histomap entity")
        if timeline_role in {"period", "both"} and document.get("end") is None:
            raise HTTPException(422, "A period overlay requires a finite end date")
        document["timeline_role"] = timeline_role
        document["manual_overrides"] = sorted(
            set(document.get("manual_overrides", [])) | {"timeline_role"}
        )
        path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
        period_id = None
        if timeline_role in {"period", "both"}:
            period_id = f"{polity_id}_period"
            periods_dir = root / "periods"
            periods_dir.mkdir(exist_ok=True)
            qid = (document.get("external_ids") or {}).get("wikidata")
            period = {
                "id": period_id,
                "canonical_name": document["canonical_name"],
                "kind": "archaeological" if "archaeological" in period_kinds else "historical",
                "start": document["start"],
                "end": document["end"],
                "start_confidence": document.get("start_confidence", "low"),
                "end_confidence": document.get("end_confidence", "low"),
                "geography": document.get("geography") or {},
                "broader_periods": [],
                "successors": [],
                "authority": "Wikidata period classification",
                "external_ids": {"wikidata": qid} if qid else {},
                "notes": "Period overlay created by an editorial period-role decision.",
                "source_urls": [f"https://www.wikidata.org/wiki/{qid}"] if qid else [],
            }
            (periods_dir / f"{period_id}.yaml").write_text(
                yaml.safe_dump(period, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            if timeline_role == "both":
                links_path = root / "period_links.yaml"
                links = yaml.safe_load(links_path.read_text(encoding="utf-8")) if links_path.exists() else []
                if not any(link.get("period_id") == period_id and link.get("entity_id") == polity_id for link in links):
                    links.append(
                        {
                            "period_id": period_id,
                            "entity_id": polity_id,
                            "relation": "part_of_periodization",
                            "evidence": "explicit",
                            "confidence": "high",
                            "source_urls": [f"https://www.wikidata.org/wiki/{qid}"] if qid else [],
                            "notes": "Same Wikidata item has distinct entity and period roles.",
                        }
                    )
                    links_path.write_text(yaml.safe_dump(links, sort_keys=False, allow_unicode=True), encoding="utf-8")
        metadata[polity_id] = document
        return {"document": document, "period_id": period_id}

    application.mount("/static", StaticFiles(directory=web_dir), name="static")

    @application.get("/", include_in_schema=False)
    async def timeline() -> FileResponse:
        return FileResponse(web_dir / "index.html")

    @application.get("/review", include_in_schema=False)
    async def review_page() -> FileResponse:
        return FileResponse(web_dir / "review.html")

    @application.get("/reviews", include_in_schema=False)
    async def reviews_home_page() -> FileResponse:
        return FileResponse(web_dir / "reviews.html")

    @application.get("/consolidation-review", include_in_schema=False)
    async def consolidation_review_page() -> FileResponse:
        return FileResponse(web_dir / "consolidation_review.html")

    @application.get("/type-review", include_in_schema=False)
    async def type_review_page() -> FileResponse:
        return FileResponse(web_dir / "type_review.html")

    @application.get("/subdivision-review", include_in_schema=False)
    async def subdivision_review_page() -> FileResponse:
        return FileResponse(web_dir / "subdivision_review.html")

    @application.get("/period-review", include_in_schema=False)
    async def period_review_page() -> FileResponse:
        return FileResponse(web_dir / "period_review.html")

    @application.get("/data.json", include_in_schema=False)
    async def data() -> FileResponse:
        path = root / "data.json"
        if not path.exists():
            raise HTTPException(404, "Run the build action first")
        return FileResponse(path)

    @application.get("/transitions.json", include_in_schema=False)
    async def transitions() -> FileResponse:
        path = root / "transitions.json"
        if not path.exists():
            raise HTTPException(404, "Run the build action first")
        return FileResponse(path)

    @application.get("/periods.json", include_in_schema=False)
    async def periods() -> FileResponse:
        path = root / "periods.json"
        if not path.exists():
            raise HTTPException(404, "Run the build action first")
        return FileResponse(path)

    @application.get("/period_links.json", include_in_schema=False)
    async def period_links() -> FileResponse:
        path = root / "period_links.json"
        if not path.exists():
            raise HTTPException(404, "Run the build action first")
        return FileResponse(path)

    @application.get("/api/reviews")
    async def reviews(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)) -> dict:
        items = [add_source_links(record, metadata) for record in review_queue[offset : offset + limit]]
        return clean_json({"total": len(review_queue), "offset": offset, "items": items})

    @application.get("/api/review-dashboard")
    async def review_dashboard() -> dict:
        refresh_type_review_queue()
        refresh_period_role_queue()
        consolidation_total = len(consolidation_review_queue())
        return {
            "pipelines": {
                "consolidation": consolidation_total,
                "entity_type": len(type_review_queue),
                "subdivision_parent": sum(
                    1 for document in metadata.values()
                    if document.get("timeline_role", "entity") != "retired"
                    and document.get("entity_type") == "subdivision"
                    and document.get("subdivision_parent_status", "pending") != "confirmed"
                ),
                "period_role": len(period_role_queue),
                "source_matching": len(review_queue),
            }
        }

    @application.get("/api/consolidation-reviews")
    async def consolidation_reviews(
        offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)
    ) -> dict:
        queue = consolidation_review_queue()
        return clean_json({"total": len(queue), "offset": offset, "items": queue[offset : offset + limit]})

    @application.post("/api/consolidation-reviews/{entity_id}")
    async def decide_consolidation_review(entity_id: str, request: ConsolidationDecision) -> dict:
        document = save_consolidation(entity_id, request.decision, request.target_id)
        return {
            "status": "saved", "entity_id": entity_id,
            "decision": request.decision, "target_id": document.get("consolidated_into"),
        }

    @application.get("/api/type-reviews")
    async def type_reviews(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)) -> dict:
        refresh_type_review_queue()
        return clean_json(
            {"total": len(type_review_queue), "offset": offset, "items": type_review_queue[offset : offset + limit]}
        )

    @application.post("/api/type-reviews/{polity_id}")
    async def decide_type_review(polity_id: str, request: EntityTypeUpdate) -> dict:
        record = next((item for item in type_review_queue if item["id"] == polity_id), None)
        if record is None:
            raise HTTPException(404, "Entity type review is not pending")
        save_entity_type(
            polity_id,
            request.entity_type,
            record.get("proposed_type"),
        )
        type_review_queue.remove(record)
        return {"status": "saved", "polity_id": polity_id, "entity_type": request.entity_type}

    @application.get("/api/subdivision-reviews")
    async def subdivision_reviews(
        offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)
    ) -> dict:
        queue = subdivision_review_queue()
        return clean_json(
            {"total": len(queue), "offset": offset, "items": queue[offset : offset + limit]}
        )

    @application.post("/api/subdivision-reviews/{polity_id}")
    async def decide_subdivision_review(
        polity_id: str, request: SubdivisionParentUpdate
    ) -> dict:
        document = save_subdivision_parent(polity_id, request.parent_id)
        return {
            "status": "saved",
            "polity_id": polity_id,
            "parent_id": document["parent"],
            "subdivision_parent_status": "confirmed",
        }

    @application.get("/api/period-role-reviews")
    async def period_role_reviews(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)) -> dict:
        refresh_period_role_queue()
        return clean_json(
            {"total": len(period_role_queue), "offset": offset, "items": period_role_queue[offset : offset + limit]}
        )

    @application.post("/api/period-role-reviews/{polity_id}")
    async def decide_period_role(polity_id: str, request: TimelineRoleUpdate) -> dict:
        refresh_period_role_queue()
        record = next((item for item in period_role_queue if item["id"] == polity_id), None)
        if record is None:
            raise HTTPException(404, "Period-role review is not pending")
        result = save_timeline_role(polity_id, request.timeline_role, record.get("period_kinds", []))
        return {
            "status": "saved",
            "polity_id": polity_id,
            "timeline_role": request.timeline_role,
            "period_id": result["period_id"],
        }

    @application.get("/api/polities/search")
    async def search_all_polities(
        q: str = Query(..., min_length=2), limit: int = Query(10, ge=1, le=25)
    ) -> dict:
        return clean_json({"query": q, "items": search_polities(q, metadata, limit)})

    @application.get("/api/options/geography")
    async def geography_options() -> dict:
        return {
            "continents": CONTINENTS,
            "countries": [
                {
                    "code": code,
                    "label": label,
                    "continents": sorted(
                        {
                            continent
                            for info in country_metadata.values()
                            if info.get("iso2") == code
                            for continent in info.get("continents", [])
                            if continent in CONTINENTS
                        }
                    ),
                }
                for code, label in sorted(country_options.items(), key=lambda item: item[1])
            ],
        }

    @application.patch("/api/polities/{polity_id}/geography")
    async def update_polity_geography(polity_id: str, request: GeographyUpdate) -> dict:
        document = metadata.get(polity_id)
        path = polities_dir / f"{polity_id}.yaml"
        if document is None or not path.exists():
            raise HTTPException(404, "Unknown Histomap entity")
        unknown_continents = sorted(set(request.continents) - set(CONTINENTS))
        unknown_countries = sorted(set(request.present_countries) - set(country_options))
        if unknown_continents:
            raise HTTPException(422, f"Unknown continents: {', '.join(unknown_continents)}")
        if unknown_countries:
            raise HTTPException(422, f"Unknown country codes: {', '.join(unknown_countries)}")
        existing = document.get("geography") or {}
        geography = Geography.model_validate(
            {
                "continents": sorted(set(request.continents)),
                "primary_continent": request.primary_continent,
                "present_countries": sorted(set(request.present_countries)),
                "centroid": existing.get("centroid"),
                "confidence": "high",
            }
        ).model_dump(mode="json", exclude_none=True)
        document["geography"] = geography
        document["manual_overrides"] = sorted(
            set(document.get("manual_overrides", [])) | {"geography"}
        )
        path.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        metadata[polity_id] = document
        return {
            "status": "saved",
            "polity_id": polity_id,
            "geography": geography,
            "manual_overrides": document["manual_overrides"],
        }

    @application.patch("/api/polities/{polity_id}/entity-type")
    async def update_entity_type(polity_id: str, request: EntityTypeUpdate) -> dict:
        document = save_entity_type(
            polity_id, request.entity_type
        )
        return {
            "status": "saved",
            "polity_id": polity_id,
            "entity_type": request.entity_type,
            "entity_type_confidence": "high",
            "manual_overrides": document["manual_overrides"],
        }

    @application.post("/api/reviews/{seshat_id}")
    async def decide_review(seshat_id: str, request: ReviewDecision) -> dict:
        record = reviews_by_id.get(seshat_id)
        if record is None:
            raise HTTPException(404, "Review is not pending")
        if request.decision == "defer":
            return {"status": "deferred", "seshat_id": seshat_id}
        decision = {"seshat_id": seshat_id, "decision": request.decision}
        if request.decision == "accept":
            target = metadata.get(request.polity_id or "")
            if target is None or target.get("eligibility") == "excluded":
                raise HTTPException(422, "polity_id must identify an eligible Histomap entity")
            decision["polity_id"] = request.polity_id
        save_decision(decision, decisions_path)
        reviews_by_id.pop(seshat_id, None)
        review_queue.remove(record)
        return {"status": "saved", **decision}

    async def run_action(action: str) -> None:
        async with job_lock:
            job.update(status="running", action=action, output="", returncode=None)
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                *ALLOWED_ACTIONS[action],
                cwd=root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            output, _ = await process.communicate()
            job.update(
                status="complete" if process.returncode == 0 else "failed",
                output=output.decode("utf-8", errors="replace")[-20000:],
                returncode=process.returncode,
            )
            if process.returncode == 0 and action == "reconcile":
                refresh_review_queue()
            elif process.returncode == 0 and action == "apply-reviews":
                refresh_separate_entities()

    @application.post("/api/actions/{action}", status_code=202)
    async def start_action(action: str) -> dict:
        if action not in ALLOWED_ACTIONS:
            raise HTTPException(404, "Unknown action")
        if job["status"] in {"queued", "running"}:
            raise HTTPException(409, f"{job['action']} is already running")
        job.update(status="queued", action=action, output="", returncode=None)
        asyncio.create_task(run_action(action))
        return {"status": "accepted", "action": action}

    @application.get("/api/actions/status")
    async def action_status() -> dict:
        return job.copy()

    @application.get("/web", include_in_schema=False)
    async def old_web_path() -> RedirectResponse:
        return RedirectResponse("/")

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server.app:app", host="127.0.0.1", port=8000, reload=False)
