"""One-shot seeding script for `Period.civilization_lane` (2026-08-31). Run
once; re-running is safe -- it only ever fills an unset (None) field, never
overwrites a value already set (whether by a human or by an earlier run of
this script).

Until this date, whether a tier=period record showed in /explore's
Civilizations & Cultures lane was computed on the fly at every build via
pipeline/build_explore_tree.py::_is_civilization_lane_period() -- a real
signal (authority == CIVILIZATION_BACKDROP_AUTHORITY) OR, when that wasn't
set, a name-substring guess ("civilization"/"culture" in canonical_name).
See ROADMAP.md's "heuristic/on-the-fly computation audit" item, the same
question already answered for linked_era_id/linked_chapter_id.

Seeds every tier=period record (not just the ones currently landing True --
an explicit False is just as much a fact worth recording as an explicit
True, and cheap to set since this is a plain boolean) with today's
_is_civilization_lane_period() result, so the field starts fully populated
and the fallback logic never actually needs to run again for anything
already on disk -- only brand-new period records will ever see it.

Not part of the recurring pipeline sequence."""

from __future__ import annotations

from pathlib import Path

import yaml

from pipeline.build_explore_tree import _is_civilization_lane_period

ROOT = Path(__file__).resolve().parent.parent
PERIODS_DIR = ROOT / "periods"


def main() -> None:
    seeded = 0
    skipped = 0
    for path in sorted(PERIODS_DIR.glob("*.yaml")):
        period = yaml.safe_load(path.read_text(encoding="utf-8"))
        if period.get("civilization_lane") is not None:
            skipped += 1
            continue
        # Raw YAML (unlike the real build, which round-trips through
        # Period.model_validate()) leaves an unset tier as None rather than
        # applying the schema's "period" default -- normalize before
        # checking, same gotcha seed_linked_era_ids.py/
        # seed_linked_chapter_ids.py already document. Only affects the
        # tier=="period" gate itself; regional_era/macro_chapter records
        # always set tier explicitly and are unaffected either way.
        normalized = {**period, "tier": period.get("tier") or "period"}
        period["civilization_lane"] = _is_civilization_lane_period(normalized)
        path.write_text(yaml.safe_dump(period, sort_keys=False, allow_unicode=True), encoding="utf-8")
        seeded += 1
    print(f"seed_civilization_lane_flags: seeded {seeded} periods, skipped {skipped} already set")


if __name__ == "__main__":
    main()
