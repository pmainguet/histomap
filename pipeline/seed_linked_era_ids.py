"""One-shot seeding script for `Polity.linked_era_id`/`Period.linked_era_id`
(2026-08-31). Run once; re-running is safe -- it only ever fills an empty
field, never overwrites a value already set (whether by a human or by an
earlier run of this script).

Until this date, /explore's era-matched band coloring was computed on the
fly at every build via a date+geography heuristic (rank_candidates, the same
one suggest_regional_eras.py uses to place an unparented period) -- see the
git history of pipeline/build_explore_tree.py's now-removed
`_linked_era_id()`. The user asked for that link to be a plain, curator-
editable field instead of a recomputed heuristic. This script seeds every
in-scope entity's field from what the heuristic would have produced, one
time, as a starting point a curator can then correct by hand (via /explore's
side-panel raw-field editor) -- it does not run as part of the regular build.

Not part of the recurring pipeline sequence."""

from __future__ import annotations

from pathlib import Path

import yaml

from pipeline.build_explore_tree import CIVILIZATION_ENTITY_TYPES, _is_civilization_lane_period, _civilization_period_source_entity_type
from pipeline.suggest_period_links import in_scope
from pipeline.suggest_regional_eras import rank_candidates
from build import load_civilization_period_role_sources

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"
PERIODS_DIR = ROOT / "periods"


def load_yaml_dir(directory: Path) -> list[dict]:
    return [yaml.safe_load(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.yaml"))]


def write_yaml(path: Path, document: dict) -> None:
    path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main() -> None:
    polities = load_yaml_dir(POLITIES_DIR)
    periods = load_yaml_dir(PERIODS_DIR)
    all_eras = [p for p in periods if p.get("tier") == "regional_era"]
    # Same "open-ended polity" fallback as best_chapter_for_polity -- derived
    # from the dataset's own latest macro-chapter end, not hardcoded.
    open_end = max(p["end"] for p in periods if p.get("tier") == "macro_chapter")

    seeded_polities = 0
    for polity in polities:
        if polity.get("linked_era_id"):
            continue
        # Civilizations & Cultures lane polities, and any other in-scope
        # (/explore-visible) polity -- coloring is now available to the
        # ordinary Polities row too, not just the civ lane, per the user's
        # explicit request ("same for polities, culture, etc").
        is_civ_lane = polity.get("entity_type") in CIVILIZATION_ENTITY_TYPES
        if not is_civ_lane and not in_scope(polity):
            continue
        candidate = {**polity, "end": polity.get("end") if polity.get("end") is not None else open_end}
        ranked = rank_candidates(candidate, all_eras)
        if not ranked:
            continue
        polity["linked_era_id"] = ranked[0]["id"]
        write_yaml(POLITIES_DIR / f"{polity['id']}.yaml", polity)
        seeded_polities += 1

    civilization_period_sources = load_civilization_period_role_sources()

    seeded_periods = 0
    for period in periods:
        if period.get("linked_era_id"):
            continue
        # _is_civilization_lane_period requires tier == "period", but raw
        # YAML (unlike the real build, which round-trips through
        # Period.model_validate()) leaves an unset tier as None rather than
        # applying the schema's "period" default -- normalize before
        # checking, or every civ-lane period whose file omits `tier` (the
        # common case) silently fails this check.
        normalized = {**period, "tier": period.get("tier") or "period"}
        is_civ_lane = _is_civilization_lane_period(normalized) or (
            _civilization_period_source_entity_type(period, civilization_period_sources) is not None
        )
        if not is_civ_lane:
            continue
        ranked = rank_candidates(period, all_eras)
        if not ranked:
            continue
        period["linked_era_id"] = ranked[0]["id"]
        write_yaml(PERIODS_DIR / f"{period['id']}.yaml", period)
        seeded_periods += 1

    print(f"seed_linked_era_ids: seeded {seeded_polities} polities and {seeded_periods} periods")


if __name__ == "__main__":
    main()
