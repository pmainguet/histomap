"""One-off migration: retire Polity.parent/subdivision_parent_status in
favor of the already-existing Polity.detail_of field -- a second, older
mechanism for "this entity nests inside that one" that turned out to
duplicate what detail_of (the September 1 merge) already covers. See
docs/plans/2026-09-04-subdivision-detail-of-merge-design.md.

Usage: python -m pipeline.migrate_parent_to_detail_of [--dry-run] [--root PATH]
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_polities(root: Path) -> dict[str, dict[str, Any]]:
    return {
        path.stem: yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for path in sorted((root / "polities").glob("*.yaml"))
    }


def main(root: Path = ROOT, *, dry_run: bool = False) -> dict[str, int]:
    """Run the one-off parent/subdivision_parent_status -> detail_of
    migration. Returns a summary dict with migrated/kept_existing_detail_of
    counts. Does not flatten or otherwise alter multi-level chains -- a
    parent target that itself has (or will separately get) detail_of set
    is preserved exactly as multi-level data, not collapsed to one level.
    See docs/plans/2026-09-04-subdivision-detail-of-merge-design.md's
    Architecture section for why."""
    polities = _load_polities(root)
    summary = {"migrated": 0, "kept_existing_detail_of": 0}
    for polity_id, document in polities.items():
        old_parent = document.get("parent")
        if not old_parent:
            continue
        summary["migrated"] += 1

        deprecated = dict(document.get("deprecated") or {})
        deprecated["parent"] = old_parent
        if document.get("subdivision_parent_status"):
            deprecated["subdivision_parent_status"] = document["subdivision_parent_status"]

        if document.get("detail_of"):
            summary["kept_existing_detail_of"] += 1
            if document["detail_of"] != old_parent:
                note = (
                    f"Migration note (parent/detail_of merge, 4 September 2026): "
                    f"the retired parent field pointed at {old_parent}, kept detail_of "
                    f"({document['detail_of']}) as the deliberately-set value instead."
                )
                document["notes"] = (document.get("notes", "").rstrip() + " " + note).strip()
        else:
            document["detail_of"] = old_parent

        document["deprecated"] = deprecated
        document.pop("parent", None)
        document.pop("subdivision_parent_status", None)

        if not dry_run:
            (root / "polities" / f"{polity_id}.yaml").write_text(
                yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = main(args.root, dry_run=args.dry_run)
    print(
        f"{'[dry run] ' if args.dry_run else ''}migrated {result['migrated']} records "
        f"({result['kept_existing_detail_of']} kept an existing detail_of)"
    )
