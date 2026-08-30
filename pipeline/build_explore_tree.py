"""Build-time step: precompute explore_tree.json, the full period hierarchy
(macro chapter -> regional era -> named period, plus polities bucketed per
chapter by historical region and by continent) that /explore renders
directly. Retires build_explore_index.py's flatter top-N summary -- the new
hierarchical /explore view needs the whole tree, not just each chapter's
top 3 entities. See docs/plans/2026-08-30-explore-hierarchy-timeline.md."""

from __future__ import annotations

from pipeline.geography_overlap import overlap_years
from pipeline.period_hierarchy import PeriodHierarchy
from pipeline.suggest_period_links import in_scope
from pipeline.suggest_regional_eras import rank_candidates


def best_chapter_for_polity(polity: dict, chapters: list[dict], open_end: int) -> dict | None:
    """Pick the macro chapter with the most date-overlap against a polity that
    has no curated period_links.yaml entry. Chapters are mutually exclusive
    and contiguous in time by construction, so this is a pure date test --
    no geography_matches call needed at chapter granularity. `open_end` is
    the fallback end year for a polity with no `end` set (an open-ended
    entity) -- derived from the tree's own chapters, not hardcoded, so it
    can never desync from the tree's actual domain."""
    polity_range = (polity["start"], polity.get("end") if polity.get("end") is not None else open_end)
    best: tuple[int, dict] | None = None
    for chapter in chapters:
        years = overlap_years(polity_range, (chapter["start"], chapter["end"]))
        if years <= 0:
            continue
        if best is None or years > best[0]:
            best = (years, chapter)
    return best[1] if best else None


def build_explore_tree(polities: list[dict], periods: list[dict], period_links: list[dict]) -> dict:
    """Precompute the full Explore page tree: 9 macro chapters, each with its
    curated regional eras, each era's curated-or-heuristic named periods, and
    each chapter's curated-or-heuristic polities bucketed by historical
    region and by continent. A polity is "curated" if it has a
    period_links.yaml entry into a period that ends up placed under this
    chapter's eras -- independent of whether that period's own era placement
    is itself curated (via broader_periods) or heuristic (via
    rank_candidates): the human-curated fact is the polity-to-period link
    itself, not the period's era nesting. This can't route through
    PeriodHierarchy.entities_under() -- that only sees graph edges present in
    the raw broader_periods/period_links.yaml data, not the heuristic
    placements this function computes itself. See
    docs/plans/2026-08-30-explore-hierarchy-timeline.md's final-review fix."""
    hierarchy = PeriodHierarchy(periods=periods, period_links=period_links, polities=polities)
    periods_by_id = {p["id"]: p for p in periods}
    all_eras = [p for p in periods if p.get("tier") == "regional_era"]
    all_periods = [p for p in periods if p.get("tier") == "period"]

    entities_by_period: dict[str, list[str]] = {}
    for link in period_links:
        entities_by_period.setdefault(link["period_id"], []).append(link["entity_id"])

    chapter_ids = hierarchy.macro_chapters()
    chapters_by_id = {cid: periods_by_id[cid] for cid in chapter_ids}
    open_end = max(chapters_by_id[cid]["end"] for cid in chapter_ids)

    # Pass 1: place every era's periods for every chapter first, then derive
    # curated polity ids from what actually landed -- must be complete for
    # every chapter before Pass 2's polity bucketing, so a polity curated
    # under chapter A is never also heuristically re-placed under chapter B.
    eras_by_chapter: dict[str, list[dict]] = {}
    for cid in chapter_ids:
        eras_by_chapter[cid] = [_era_entry(periods_by_id[eid], []) for eid in hierarchy.children(cid)]

    era_to_chapter: dict[str, str] = {
        era["id"]: cid for cid, eras in eras_by_chapter.items() for era in eras
    }

    unmatched_periods = 0
    for period in all_periods:
        if period.get("broader_periods"):
            era_id = period["broader_periods"][0]
            curated = True
        else:
            ranked = rank_candidates(period, all_eras)
            if not ranked:
                unmatched_periods += 1
                continue
            era_id = ranked[0]["id"]
            curated = False
        target_chapter = era_to_chapter.get(era_id)
        if target_chapter is None:
            continue  # era isn't nested under any chapter -- shouldn't happen for a valid era, but be defensive
        era_entry = next(e for e in eras_by_chapter[target_chapter] if e["id"] == era_id)
        era_entry["periods"].append(_period_entry(period, curated=curated))
    if unmatched_periods:
        print(f"build_explore_tree: {unmatched_periods} periods placed under no era (no geography/date match)")

    chapter_curated_ids: dict[str, set[str]] = {}
    for cid in chapter_ids:
        curated_ids: set[str] = set()
        for era_entry in eras_by_chapter[cid]:
            for period_entry in era_entry["periods"]:
                curated_ids.update(entities_by_period.get(period_entry["id"], []))
        chapter_curated_ids[cid] = curated_ids
    all_curated_ids: set[str] = set().union(*chapter_curated_ids.values()) if chapter_curated_ids else set()

    # Pass 2: bucket polities per chapter by region, using the curated ids
    # from Pass 1.
    chapters_out = []
    for cid in chapter_ids:
        chapter = chapters_by_id[cid]
        by_region: dict[str, list[dict]] = {}
        by_continent: dict[str, list[dict]] = {}
        for polity in polities:
            if not in_scope(polity):
                continue
            polity_id = polity["id"]
            is_curated = polity_id in chapter_curated_ids[cid]
            if not is_curated:
                if polity_id in all_curated_ids:
                    continue  # curated under a *different* chapter
                best = best_chapter_for_polity(polity, [chapters_by_id[c] for c in chapter_ids], open_end)
                if best is None or best["id"] != cid:
                    continue
            geo = polity.get("geography") or {}
            region = geo.get("primary_historical_region") or (geo.get("historical_regions") or [None])[0] or "unclassified"
            continent = geo.get("primary_continent") or (geo.get("continents") or [None])[0] or "unclassified"
            entry = _polity_entry(polity, curated=is_curated)
            by_region.setdefault(region, []).append(entry)
            by_continent.setdefault(continent, []).append(entry)

        for bucket in (*by_region.values(), *by_continent.values()):
            bucket.sort(key=lambda e: (e["start"], e["id"]))

        chapters_out.append({
            "id": cid,
            "canonical_name": chapter["canonical_name"],
            "start": chapter["start"],
            "end": chapter["end"],
            "eras": eras_by_chapter[cid],
            "polities_by_historical_region": by_region,
            "polities_by_continent": by_continent,
        })

    earliest_chapter = min(chapters_out, key=lambda c: c["start"])
    latest_end = max((c["end"] for c in chapters_out), default=0)
    return {
        "axis": {
            "domain_start": earliest_chapter["start"],
            "domain_end": latest_end,
            "segment_break": earliest_chapter["end"],
        },
        "chapters": chapters_out,
    }


def _era_entry(era: dict, periods_out: list[dict]) -> dict:
    """Build a JSON-serializable dict entry for a regional-era node in the explore tree."""
    return {
        "id": era["id"],
        "canonical_name": era["canonical_name"],
        "start": era["start"],
        "end": era["end"],
        "periods": periods_out,
    }


def _period_entry(period: dict, curated: bool) -> dict:
    """Build a JSON-serializable dict entry for a named-period node with its curated/heuristic flag."""
    return {
        "id": period["id"],
        "canonical_name": period["canonical_name"],
        "start": period["start"],
        "end": period["end"],
        "curated": curated,
    }


def _polity_entry(polity: dict, curated: bool) -> dict:
    """Build a JSON-serializable dict entry for a polity with its curated/heuristic flag."""
    return {
        "id": polity["id"],
        "canonical_name": polity["canonical_name"],
        "start": polity["start"],
        "end": polity.get("end"),
        "curated": curated,
        "present_countries": (polity.get("geography") or {}).get("present_countries") or [],
    }
