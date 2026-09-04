"""One-off migration: retire Polity.visibility_tier/visibility_override,
preserving old values under deprecated for audit. See
docs/plans/2026-09-05-retire-visibility-tier-design.md.

Usage: python -m pipeline.migrate_visibility_tier [--dry-run] [--root PATH]
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
    """Run the one-off visibility_tier/visibility_override -> deprecated
    migration. Returns a summary dict with a migrated count."""
    polities = _load_polities(root)
    summary = {"migrated": 0}
    for polity_id, document in polities.items():
        has_tier = "visibility_tier" in document
        has_override = "visibility_override" in document
        if not has_tier and not has_override:
            continue
        summary["migrated"] += 1

        deprecated = dict(document.get("deprecated") or {})
        if has_tier:
            deprecated["visibility_tier"] = document.pop("visibility_tier")
        if has_override:
            deprecated["visibility_override"] = document.pop("visibility_override")
        document["deprecated"] = deprecated

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
    print(f"{'[dry run] ' if args.dry_run else ''}migrated {result['migrated']} records")
