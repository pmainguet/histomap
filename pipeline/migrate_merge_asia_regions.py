"""One-off migration: fold the south_asia and southeast_asia
historical-region buckets into east_asia (merged 7 September 2026 --
west_asia/central_asia/east_asia is now the full Asian split) on every
polity/period record that still carries the old ids in
geography.historical_regions or geography.primary_historical_region.
Rewrites, dedupes, and re-sorts historical_regions; remaps
primary_historical_region the same way. Same pattern as
pipeline/migrate_period_kind_to_deprecated.py."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent

RETIRED_REGIONS = {"south_asia", "southeast_asia"}
MERGED_REGION = "east_asia"


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _merge_regions(regions: list[str]) -> list[str]:
    merged = {MERGED_REGION if region in RETIRED_REGIONS else region for region in regions}
    return sorted(merged)


def _migrate_directory(directory: Path, *, dry_run: bool) -> int:
    migrated = 0
    for path in sorted(directory.glob("*.yaml")):
        document = _load_yaml(path)
        geography = document.get("geography") or {}
        regions = geography.get("historical_regions") or []
        primary = geography.get("primary_historical_region")
        touches_retired = any(region in RETIRED_REGIONS for region in regions) or primary in RETIRED_REGIONS
        if not touches_retired:
            continue
        geography["historical_regions"] = _merge_regions(regions)
        if primary in RETIRED_REGIONS:
            geography["primary_historical_region"] = MERGED_REGION
        document["geography"] = geography
        migrated += 1
        if not dry_run:
            path.write_text(
                yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
    return migrated


def main(root: Path = ROOT, *, dry_run: bool = False) -> dict[str, int]:
    return {
        "polities_migrated": _migrate_directory(root / "polities", dry_run=dry_run),
        "periods_migrated": _migrate_directory(root / "periods", dry_run=dry_run),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = main(dry_run=args.dry_run)
    suffix = " (dry run)" if args.dry_run else ""
    print(
        f"Migrated {result['polities_migrated']} polity and "
        f"{result['periods_migrated']} period record(s){suffix}"
    )
