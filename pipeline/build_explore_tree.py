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


def best_chapter_for_polity(polity: dict, chapters: list[dict]) -> dict | None:
    """Pick the macro chapter with the most date-overlap against a polity that
    has no curated period_links.yaml entry. Chapters are mutually exclusive
    and contiguous in time by construction, so this is a pure date test --
    no geography_matches call needed at chapter granularity."""
    polity_range = (polity["start"], polity.get("end") if polity.get("end") is not None else 2100)
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
    region and by continent. See docs/plans/2026-08-30-explore-hierarchy-timeline.md
    Task 1 Step 3 for the placement rules this implements."""
    hierarchy = PeriodHierarchy(periods=periods, period_links=period_links, polities=polities)
    periods_by_id = {p["id"]: p for p in periods}
    polities_by_id = {p["id"]: p for p in polities}
    all_eras = [p for p in periods if p.get("tier") == "regional_era"]
    all_periods = [p for p in periods if p.get("tier") == "period"]

    chapter_ids = hierarchy.macro_chapters()
    chapters_by_id = {cid: periods_by_id[cid] for cid in chapter_ids}

    curated_polity_ids: set[str] = set()
    for cid in chapter_ids:
        curated_polity_ids.update(hierarchy.entities_under(cid))

    unmatched_periods = 0
    chapters_out = []
    for cid in chapter_ids:
        chapter = chapters_by_id[cid]
        chapter_curated_ids = set(hierarchy.entities_under(cid))  # computed once per chapter, not per polity
        eras_out = []
        for era_id in hierarchy.children(cid):
            era = periods_by_id[era_id]
            periods_out = []
            for period_id in hierarchy.children(era_id):
                period = periods_by_id[period_id]
                periods_out.append(_period_entry(period, curated=True))
            eras_out.append(_era_entry(era, periods_out))
        for period in all_periods:
            if period.get("broader_periods"):
                continue  # curated placement already covered by the loop above
            ranked = rank_candidates(period, all_eras)
            if not ranked or ranked[0]["id"] not in {e["id"] for e in eras_out}:
                # Either no geography/date match at all, or the best match
                # isn't one of this chapter's eras -- skip; a period with no
                # match anywhere is counted once, globally, below.
                continue
            era_entry = next(e for e in eras_out if e["id"] == ranked[0]["id"])
            era_entry["periods"].append(_period_entry(period, curated=False))

        by_region: dict[str, list[dict]] = {}
        by_continent: dict[str, list[dict]] = {}
        for polity in polities:
            if not in_scope(polity):
                continue
            polity_id = polity["id"]
            is_curated = polity_id in chapter_curated_ids
            if not is_curated:
                if polity_id in curated_polity_ids:
                    continue  # curated under a *different* chapter
                best = best_chapter_for_polity(polity, [chapters_by_id[c] for c in chapter_ids])
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
            "eras": eras_out,
            "polities_by_historical_region": by_region,
            "polities_by_continent": by_continent,
        })

    for period in all_periods:
        if period.get("broader_periods"):
            continue
        ranked = rank_candidates(period, all_eras)
        if not ranked:
            unmatched_periods += 1
    if unmatched_periods:
        print(f"build_explore_tree: {unmatched_periods} periods placed under no era (no geography/date match)")

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
    }
