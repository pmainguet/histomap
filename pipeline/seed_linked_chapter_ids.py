"""One-shot seeding script for `Polity.linked_chapter_id`/`Period.linked_chapter_id`
(2026-08-31). Run once; re-running is safe -- it only ever fills an empty
field, never overwrites a value already set (whether by a human or by an
earlier run of this script).

Until this date, /explore's macro-chapter placement was computed on the fly
at every build via a pure date-overlap heuristic (best_chapter_for_polity /
_best_chapter_for_range in pipeline/build_explore_tree.py) for any entity with
no curated period_links.yaml route to a chapter -- and for every
Civilizations & Cultures lane item, which had no curated chapter route at
all. See ROADMAP.md's "heuristic/on-the-fly computation audit" item, the
same question already answered for linked_era_id.

This script runs the REAL build_explore_tree() once against the current,
unseeded dataset (rather than re-implementing its curated/heuristic logic
independently, which would risk silently drifting from what the actual build
does) and reads back, per entity, which chapter it actually landed under and
whether that placement was curated or heuristic. Every Civilizations &
Cultures lane item is always heuristic today (entity_type/authority being
"curated" is a different fact -- whether the entity_type classification
itself is reviewed -- from whether its *chapter* placement is), so every one
gets seeded unconditionally, matching seed_linked_era_ids.py's own precedent.
Ordinary Polities-row entries only get seeded when NOT already reachable via
a real period_links.yaml route (heuristic-placed, `curated: False` in the
tree's own output).

Not part of the recurring pipeline sequence."""

from __future__ import annotations

from pathlib import Path

import yaml

from build import load_civilization_period_role_sources
from pipeline.build_explore_tree import build_explore_tree

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"
PERIODS_DIR = ROOT / "periods"
PERIOD_LINKS_PATH = ROOT / "period_links.yaml"


def load_yaml_dir(directory: Path) -> list[dict]:
    return [yaml.safe_load(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.yaml"))]


def write_yaml(path: Path, document: dict) -> None:
    path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main() -> None:
    polities = load_yaml_dir(POLITIES_DIR)
    periods = load_yaml_dir(PERIODS_DIR)
    # Raw YAML (unlike the real build, which round-trips through
    # Period.model_validate()) leaves an unset tier as None rather than
    # applying the schema's "period" default -- normalize before calling
    # build_explore_tree(), or every civ-lane period whose file omits `tier`
    # (the common case) silently fails _is_civilization_lane_period's check.
    # Same gotcha as seed_linked_era_ids.py. Keep the *original* dicts for
    # writing back, though -- normalizing them would bake an explicit
    # `tier: period` into files that currently rely on the schema default,
    # an unrelated change this script has no business making.
    normalized_periods = [{**p, "tier": p.get("tier") or "period"} for p in periods]
    period_links = yaml.safe_load(PERIOD_LINKS_PATH.read_text(encoding="utf-8")) or []
    civilization_period_sources = load_civilization_period_role_sources()

    tree = build_explore_tree(polities, normalized_periods, period_links, civilization_period_sources)

    # entity_id -> chapter_id, split by whether the real build's own logic
    # already considers the placement curated (skip -- has a real route
    # already) or heuristic (seed it).
    heuristic_polity_chapter: dict[str, str] = {}
    civ_lane_chapter: dict[str, str] = {}
    for chapter in tree["chapters"]:
        cid = chapter["id"]
        for bucket in chapter["polities_by_historical_region"].values():
            for entry in bucket:
                if not entry["curated"]:
                    heuristic_polity_chapter[entry["id"]] = cid
        for entry in chapter["civilizations"]:
            civ_lane_chapter[entry["id"]] = cid

    polities_by_id = {p["id"]: p for p in polities}
    periods_by_id = {p["id"]: p for p in periods}

    seeded_polities = 0
    for entity_id, chapter_id in {**heuristic_polity_chapter, **{
        eid: cid for eid, cid in civ_lane_chapter.items() if eid in polities_by_id
    }}.items():
        polity = polities_by_id.get(entity_id)
        if polity is None or polity.get("linked_chapter_id"):
            continue
        polity["linked_chapter_id"] = chapter_id
        write_yaml(POLITIES_DIR / f"{entity_id}.yaml", polity)
        seeded_polities += 1

    seeded_periods = 0
    for entity_id, chapter_id in civ_lane_chapter.items():
        period = periods_by_id.get(entity_id)
        if period is None or period.get("linked_chapter_id"):
            continue
        period["linked_chapter_id"] = chapter_id
        write_yaml(PERIODS_DIR / f"{entity_id}.yaml", period)
        seeded_periods += 1

    print(f"seed_linked_chapter_ids: seeded {seeded_polities} polities and {seeded_periods} periods")


if __name__ == "__main__":
    main()
