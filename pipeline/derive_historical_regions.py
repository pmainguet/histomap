"""Pipeline step: derive historical_regions/primary_historical_region from
present_countries (falling back to nothing, never to continent -- continent
is much coarser and a wrong specific region is worse than an honestly-empty
one). Only fills gaps; never overwrites a manually-set value (checks
manual_overrides, same convention as enrich_geography.py)."""

from __future__ import annotations

from pathlib import Path

import yaml

from pipeline.historical_regions import historical_region_for_country

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"
PERIODS_DIR = ROOT / "periods"
REPORT_PATH = ROOT / "reports" / "historical_region_coverage.md"


def region_for_document(document: dict) -> list[str]:
    countries = (document.get("geography") or {}).get("present_countries") or []
    regions = {historical_region_for_country(c) for c in countries}
    regions.discard(None)
    return sorted(regions)


def _apply(directory: Path) -> tuple[int, int]:
    updated = 0
    total = 0
    for path in sorted(directory.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        total += 1
        if "geography" not in document:
            continue
        if "historical_region" in (document.get("manual_overrides") or []):
            continue
        if document["geography"].get("historical_regions"):
            continue
        regions = region_for_document(document)
        if not regions:
            continue
        document["geography"]["historical_regions"] = regions
        if len(regions) == 1:
            document["geography"]["primary_historical_region"] = regions[0]
        path.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        updated += 1
    return updated, total


def main() -> None:
    polity_updated, polity_total = _apply(POLITIES_DIR)
    period_updated, period_total = _apply(PERIODS_DIR)
    REPORT_PATH.write_text(
        "# Historical region coverage\n\n"
        f"- Polities updated this run: {polity_updated} / {polity_total}\n"
        f"- Periods updated this run: {period_updated} / {period_total}\n\n"
        "Derived only from present_countries via pipeline/historical_regions.py's "
        "starter lookup table (23 regions, ~180 country codes) -- records with no "
        "present_countries, or whose countries aren't in the table yet, are left "
        "unset rather than guessed. Growing the table is cheap and safe to rerun.\n",
        encoding="utf-8",
    )
    print(f"polities: {polity_updated}/{polity_total} updated; periods: {period_updated}/{period_total} updated")


if __name__ == "__main__":
    main()
