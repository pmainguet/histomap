"""One-shot seeding script for ordinary (non-civilization-lane) `Period.broader_periods`
(2026-08-31). Run once; re-running is safe -- it only ever fills a period
that currently has none, never overwrites one already set (whether by a
human or an earlier run of this script).

`Period.broader_periods` already exists as a real, curator-editable field --
this isn't a missing-field problem like linked_era_id/linked_chapter_id/
civilization_lane were. The gap is a curation backlog: any ordinary period
without it set falls back, silently, on every build, to
pipeline/build_explore_tree.py's `rank_candidates()` date+geography-overlap
heuristic (era_to_chapter placement's `curated = False` branch) --
identical machinery to what linked_era_id used to run. See ROADMAP.md's
"heuristic/on-the-fly computation audit" item.

Converts today's best-guess `rank_candidates()` picks into real
`broader_periods` values for every ordinary period lacking one, the same way
seed_linked_era_ids.py did for linked_era_id. Deliberately excludes
Civilizations & Cultures lane periods (`civilization_lane`/
`_is_civilization_lane_period`) -- broader_periods -> era nesting is a
Period-row-only concept; the civ lane places itself by chapter alone (see
linked_chapter_id) and never nests under an era.

CAUTION on re-running: `periods/early_dynastic_mesopotamia.yaml` had
`broader_periods: []` set explicitly (not just absent) earlier this session,
as a deliberate flag -- its real relationship is "phase of Sumer" (a
civilization/polity), which broader_periods has no way to express (see
ROADMAP.md's "period can subdivide a civilization/polity" item, still open);
leaving it empty was marking that era-nesting is the wrong model for it, not
"not curated yet". This script can't tell the two apart (an empty list is
indistinguishable from a merely-absent one) and will happily overwrite it
with the heuristic's current guess -- it did, the first time this ran, and
that specific file's change was reverted by hand afterward. If re-running,
check that file again before trusting the diff.

Not part of the recurring pipeline sequence."""

from __future__ import annotations

from pathlib import Path

import yaml

from pipeline.build_explore_tree import _is_civilization_lane_period, _civilization_period_source_entity_type
from pipeline.suggest_regional_eras import rank_candidates
from build import load_civilization_period_role_sources

ROOT = Path(__file__).resolve().parent.parent
PERIODS_DIR = ROOT / "periods"


def main() -> None:
    periods = [
        yaml.safe_load(path.read_text(encoding="utf-8")) for path in sorted(PERIODS_DIR.glob("*.yaml"))
    ]
    all_eras = [p for p in periods if p.get("tier") == "regional_era"]
    civilization_period_sources = load_civilization_period_role_sources()

    seeded = 0
    unmatched = 0
    for path, period in zip(sorted(PERIODS_DIR.glob("*.yaml")), periods, strict=True):
        if period.get("broader_periods"):
            continue
        # Same raw-YAML tier-normalization gotcha the other seeding scripts
        # already document -- only affects the tier=="period" gate.
        normalized = {**period, "tier": period.get("tier") or "period"}
        if normalized.get("tier") != "period":
            continue  # regional_era/macro_chapter nodes don't nest under an era themselves
        is_civ_lane = _is_civilization_lane_period(normalized) or (
            _civilization_period_source_entity_type(period, civilization_period_sources) is not None
        )
        if is_civ_lane:
            continue
        ranked = rank_candidates(period, all_eras)
        if not ranked:
            unmatched += 1
            continue
        period["broader_periods"] = [ranked[0]["id"]]
        path.write_text(yaml.safe_dump(period, sort_keys=False, allow_unicode=True), encoding="utf-8")
        seeded += 1

    print(f"seed_broader_periods: seeded {seeded} periods, {unmatched} still unmatched (no geography/date match)")


if __name__ == "__main__":
    main()
