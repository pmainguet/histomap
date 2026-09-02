"""One-off migration: retire the phase_of/part_of consolidation_status
mechanisms in favor of Polity.detail_of, preserving every old field value
under Polity.deprecated. See docs/plans/2026-09-01-detail-of-merge-design.md.

Usage: python -m pipeline.migrate_detail_of [--dry-run] [--root PATH]
"""
import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from pipeline.backfill_entity_types import normalized_relationship_kind

ROOT = Path(__file__).resolve().parent.parent


def _load_polities(root: Path) -> dict[str, dict[str, Any]]:
    return {
        path.stem: yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for path in sorted((root / "polities").glob("*.yaml"))
    }


def _write_polity(root: Path, polity_id: str, document: dict[str, Any], *, dry_run: bool) -> None:
    if dry_run:
        return
    (root / "polities" / f"{polity_id}.yaml").write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def _migrate_phase_of(root: Path, polity_id: str, document: dict[str, Any], *, dry_run: bool) -> None:
    """Restore a phase_of-consolidated polity to a live Polity: snapshot the
    old consolidation_status/consolidated_into and its generated Period
    record + period_links.yaml row into `deprecated`, set `detail_of`, and
    un-retire it. Deletes the generated period file and link (their content
    lives on in `deprecated`)."""
    period_path = root / "periods" / f"{polity_id}_period.yaml"
    period = yaml.safe_load(period_path.read_text(encoding="utf-8")) if period_path.exists() else None

    links_path = root / "period_links.yaml"
    links = (yaml.safe_load(links_path.read_text(encoding="utf-8")) or []) if links_path.exists() else []
    matching_link = next(
        (link for link in links if link.get("period_id") == f"{polity_id}_period"
         and link.get("relation") == "phase_of"),
        None,
    )
    remaining_links = [link for link in links if link is not matching_link]

    deprecated = dict(document.get("deprecated") or {})
    deprecated["consolidation_status"] = document.get("consolidation_status")
    deprecated["consolidated_into"] = document.get("consolidated_into")
    if period is not None:
        deprecated["period"] = period
    if matching_link is not None:
        deprecated["period_link"] = matching_link

    target_id = document.get("consolidated_into")
    document["detail_of"] = target_id
    document["deprecated"] = deprecated
    document.pop("consolidation_status", None)
    document.pop("consolidated_into", None)
    document["timeline_role"] = "entity"

    _write_polity(root, polity_id, document, dry_run=dry_run)
    if not dry_run:
        if period_path.exists():
            period_path.unlink()
        links_path.write_text(yaml.safe_dump(remaining_links, sort_keys=False), encoding="utf-8")
        json_path = root / "period_links.json"
        if json_path.exists():
            json_path.write_text(json.dumps(remaining_links), encoding="utf-8")


def _migrate_part_of(root: Path, polity_id: str, document: dict[str, Any], *, dry_run: bool) -> None:
    """Restore a part_of-consolidated subdivision to a live Polity: snapshot
    the old consolidation_status/parent/subdivision_parent_status/entity_type
    into `deprecated`, set `detail_of` from the old `parent`, and revert
    `entity_type` to `polity` -- entity_type is now fully decoupled from this
    relationship, staying /subdivision-review's own concern."""
    deprecated = dict(document.get("deprecated") or {})
    deprecated["consolidation_status"] = document.get("consolidation_status")
    deprecated["parent"] = document.get("parent")
    deprecated["subdivision_parent_status"] = document.get("subdivision_parent_status")
    deprecated["entity_type"] = document.get("entity_type")

    document["detail_of"] = document.get("parent")
    document["deprecated"] = deprecated
    document.pop("consolidation_status", None)
    document.pop("parent", None)
    document.pop("subdivision_parent_status", None)
    document["entity_type"] = "polity"

    _write_polity(root, polity_id, document, dry_run=dry_run)


def _renormalize_relationships(
    root: Path, polities: dict[str, dict[str, Any]], *, dry_run: bool
) -> int:
    """part_of migration reverts entity_type from subdivision back to
    polity -- any relationship whose `kind` was chosen for the old
    subdivision/polity pairing (administrative_part_of, cultural_sequence)
    is now invalid for the new pairing, whether the relationship lives on
    the reverted entity itself (as source) or on another entity that
    references it (as target). Reuses normalized_relationship_kind(), the
    exact same rule save_entity_type() applies for a live manual
    entity-type edit, over every polity's relationships -- not just the
    migrated ones -- since a third entity can reference a migrated one.
    Returns the number of polities whose relationships changed."""
    changed_count = 0
    for polity_id, document in polities.items():
        relationships = document.get("relationships") or []
        if not relationships:
            continue
        normalized = []
        changed = False
        for relationship in relationships:
            relationship = dict(relationship)
            target = polities.get(relationship.get("target"))
            if target is None:
                normalized.append(relationship)
                continue
            new_kind = normalized_relationship_kind(
                document.get("entity_type", "polity"),
                target.get("entity_type", "polity"),
                relationship.get("kind"),
            )
            if new_kind != relationship.get("kind"):
                changed = True
            relationship["kind"] = new_kind
            normalized.append(relationship)
        if changed:
            document["relationships"] = normalized
            changed_count += 1
            _write_polity(root, polity_id, document, dry_run=dry_run)
    return changed_count


def main(root: Path = ROOT, *, dry_run: bool = False) -> dict[str, int]:
    """Run the one-off phase_of/part_of -> detail_of migration. Returns a
    summary dict with migrated_phase_of/migrated_part_of/
    relationships_renormalized counts."""
    polities = _load_polities(root)
    summary = {"migrated_phase_of": 0, "migrated_part_of": 0}
    any_part_of = False
    for polity_id, document in polities.items():
        status = document.get("consolidation_status")
        if status == "phase_of":
            _migrate_phase_of(root, polity_id, document, dry_run=dry_run)
            summary["migrated_phase_of"] += 1
        elif status == "part_of":
            _migrate_part_of(root, polity_id, document, dry_run=dry_run)
            summary["migrated_part_of"] += 1
            any_part_of = True
    if any_part_of:
        summary["relationships_renormalized"] = _renormalize_relationships(
            root, polities, dry_run=dry_run
        )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = main(args.root, dry_run=args.dry_run)
    print(f"{'[dry run] ' if args.dry_run else ''}migrated {result['migrated_phase_of']} phase_of "
          f"and {result['migrated_part_of']} part_of records")
