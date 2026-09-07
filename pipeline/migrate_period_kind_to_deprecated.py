"""One-off migration: move Period.kind (retired 7 September 2026 -- the
historical/archaeological/protohistorical/prehistorical classification is
no longer schema-validated) into deprecated.kind on every period record
that still carries it, preserving an existing deprecated bucket rather
than overwriting it. Same pattern as
pipeline/migrate_parent_to_detail_of.py and
pipeline/backfill_promoted_from.py."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def main(root: Path = ROOT, *, dry_run: bool = False) -> dict[str, int]:
    summary = {"migrated": 0}
    for path in sorted((root / "periods").glob("*.yaml")):
        document = _load_yaml(path)
        if "kind" not in document:
            continue
        deprecated = dict(document.get("deprecated") or {})
        deprecated["kind"] = document.pop("kind")
        document["deprecated"] = deprecated
        summary["migrated"] += 1
        if not dry_run:
            path.write_text(
                yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = main(dry_run=args.dry_run)
    print(f"Migrated {result['migrated']} period record(s)" + (" (dry run)" if args.dry_run else ""))
