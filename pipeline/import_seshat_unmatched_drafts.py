"""One-shot import for reports/seshat_unmatched_drafts.yaml -- Seshat source
records that never matched an existing Histomap entity during reconciliation
(pipeline/reconcile.py's "unmatched" outcome). Unlike seshat_separate_entity_
drafts.yaml (consumed by apply_review_decisions.py, the "keep as separate
entity" outcome of a human review decision), nothing downstream ever reads
this file -- these 34 records were sitting inert with no path into the
dataset.

Writes each as a minimal draft polities/*.yaml, deliberately left at schema
defaults for entity_type (`polity`) and entity_type_confidence (`low`).
Low confidence alone does not surface a record in /type-review, though --
that queue is driven by reports/entity_type_review.jsonl, itself normally
generated from Wikidata P31/P279 type evidence (pipeline/wd_to_yaml.py).
These drafts have no Wikidata item at all, so this script also appends one
honest entry per draft to that file: proposed_type "archaeological_horizon"
(a reasonable default reading of most of these records -- narrow Seshat NGA
phases like Erligang or Badarian, not single weight-bearing political
actors) with confidence "low" and a reason that says plainly there is no
automated evidence behind the proposal, so nothing here misrepresents
Wikidata evidence that doesn't exist. visibility_tier stays at its default
(`detailed`, no override), so none of these clutter /explore's default view
until reviewed. Idempotent: skips any id whose polities/*.yaml already
exists, and separately skips any id already present in
entity_type_review.jsonl, so reruns after partial review are safe.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from schema import Polity

ROOT = Path(__file__).resolve().parent.parent
DRAFTS_PATH = ROOT / "reports" / "seshat_unmatched_drafts.yaml"
POLITIES_DIR = ROOT / "polities"
TYPE_REVIEW_PATH = ROOT / "reports" / "entity_type_review.jsonl"


def sanitize_id(raw_id: str) -> str:
    """Strip characters the schema's snake_case id pattern rejects.

    Two of the 34 drafts carry a literal ``*`` from their Seshat NGA code
    (e.g. ``IqEDyn*``, denoting an inferred/expanded polity in Seshat's own
    convention) baked into the generated id -- the original code, ``*``
    included, stays in external_ids.seshat for traceability; only the id
    itself needs to be a valid identifier.
    """
    return re.sub(r"[^a-z0-9_]", "", raw_id)


def main() -> None:
    drafts = [
        document
        for document in yaml.safe_load_all(DRAFTS_PATH.read_text(encoding="utf-8"))
        if document
    ]
    written = 0
    skipped = 0
    for draft in drafts:
        entity_id = sanitize_id(draft["id"])
        path = POLITIES_DIR / f"{entity_id}.yaml"
        if path.exists():
            skipped += 1
            continue
        document = {
            "id": entity_id,
            "canonical_name": draft["canonical_name"],
            "external_ids": {"seshat": draft["external_ids"]["seshat"]},
            "start": draft["start"],
            "end": draft.get("end"),
            "start_confidence": draft["start_confidence"],
            "end_confidence": draft["end_confidence"],
            "sources": draft.get("sources") or ["seshat"],
            "notes": draft.get("notes", ""),
        }
        Polity.model_validate(document)  # fail loudly before writing anything malformed
        path.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        written += 1
    print(f"wrote {written} draft polities, skipped {skipped} already present (of {len(drafts)} total)")

    existing_entries = []
    existing_review_ids = set()
    if TYPE_REVIEW_PATH.exists():
        for line in TYPE_REVIEW_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                existing_entries.append(record)
                existing_review_ids.add(record["id"])

    queued = 0
    for draft in drafts:
        entity_id = sanitize_id(draft["id"])
        if entity_id in existing_review_ids:
            continue
        existing_entries.append(
            {
                "id": entity_id,
                "canonical_name": draft["canonical_name"],
                "wikidata": None,
                "proposed_type": "archaeological_horizon",
                "confidence": "low",
                "source_qids": [],
                "reason": "Seshat-only draft with no Wikidata item, imported via "
                "pipeline/import_seshat_unmatched_drafts.py -- no automated type "
                "evidence available; read the record and choose the correct type "
                "by hand.",
                "reconsideration": False,
                "requires_parent_review": False,
            }
        )
        queued += 1
    if queued:
        existing_entries.sort(key=lambda record: record["id"])
        TYPE_REVIEW_PATH.write_text(
            "\n".join(json.dumps(record, ensure_ascii=False) for record in existing_entries) + "\n",
            encoding="utf-8",
        )
    print(f"queued {queued} new /type-review entries, {len(drafts) - queued} already present")


if __name__ == "__main__":
    main()
