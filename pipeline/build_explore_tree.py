"""Build-time step: precompute explore_tree.json, the full period hierarchy
(macro chapter -> regional era -> named period, plus polities bucketed per
chapter by historical region and by continent, plus a flat Civilizations &
Cultures lane per chapter) that /explore renders directly. Retires
build_explore_index.py's flatter top-N summary -- the new hierarchical
/explore view needs the whole tree, not just each chapter's top 3 entities.
See docs/plans/2026-08-30-explore-hierarchy-timeline.md."""

from __future__ import annotations

from pipeline.geography_overlap import overlap_years
from pipeline.period_hierarchy import PeriodHierarchy
from pipeline.suggest_period_links import in_scope
from pipeline.suggest_regional_eras import rank_candidates

AUTO_GENERATED_AUTHORITY = "Histomap editorial: auto-generated continent x chapter node"

# Polity.entity_type values that mean "not really a weight-bearing political
# entity" -- these render in the Civilizations & Cultures lane instead of the
# Polities row. See ROADMAP.md item 4 and the /explore lane-separation design.
CIVILIZATION_ENTITY_TYPES = {"civilization", "culture", "people", "tribe"}


def _best_chapter_for_range(value_range: tuple[int, int], chapters: list[dict]) -> dict | None:
    """Pick the macro chapter with the most date-overlap against an arbitrary
    (start, end) range. Chapters are mutually exclusive and contiguous in
    time by construction, so this is a pure date test -- no geography_matches
    call needed at chapter granularity. Shared by best_chapter_for_polity
    (which derives its range from a polity, handling the open-ended-entity
    fallback) and the Civilizations & Cultures lane's period placement (which
    needs no such fallback -- Period.end is never None)."""
    best: tuple[int, dict] | None = None
    for chapter in chapters:
        years = overlap_years(value_range, (chapter["start"], chapter["end"]))
        if years <= 0:
            continue
        if best is None or years > best[0]:
            best = (years, chapter)
    return best[1] if best else None


def best_chapter_for_polity(polity: dict, chapters: list[dict], open_end: int) -> dict | None:
    """Pick the macro chapter with the most date-overlap against a polity that
    has no curated period_links.yaml entry. `open_end` is the fallback end
    year for a polity with no `end` set (an open-ended entity) -- derived
    from the tree's own chapters, not hardcoded, so it can never desync from
    the tree's actual domain."""
    polity_range = (polity["start"], polity.get("end") if polity.get("end") is not None else open_end)
    return _best_chapter_for_range(polity_range, chapters)


# Authority string stamped on a period generated from an entity_type-tagged
# polity that was demoted to a pure context band (its actual political
# weight lives in separate phase polities instead, e.g. Ancient Egypt's
# weight lives in Old/Middle/New Kingdom of Egypt, Babylonia's in
# Old/Neo-Babylonian Empire) -- see the matching note text in each such
# period's own file. A real structural signal, unlike the name heuristic
# below -- added after discovering ancient_egypt_period/babylonia_period/
# chinese_empire_period had silently fallen out of the Civilizations &
# Cultures lane once their source polities were deleted (see ONTOLOGY.md's
# "Polity/period duality" section).
CIVILIZATION_BACKDROP_AUTHORITY = "Histomap editorial: civilization-as-backdrop"


def _is_civilization_lane_period(period: dict) -> bool:
    """A tier=period record that belongs in the Civilizations & Cultures
    lane rather than the plain Period row: either it carries
    CIVILIZATION_BACKDROP_AUTHORITY (a real signal), or its canonical_name
    suggests civilization/culture -- e.g. "Minoan civilization", "Etruscan
    civilization" (a name-pattern heuristic/guess, since Period has no
    entity_type-like field of its own). tier=period only -- never
    regional_era/macro_chapter, which are structural grouping nodes, not
    entities."""
    if period.get("tier") != "period":
        return False
    if period.get("authority") == CIVILIZATION_BACKDROP_AUTHORITY:
        return True
    name = period.get("canonical_name", "").lower()
    return "civilization" in name or "culture" in name


def _civilization_period_source_entity_type(period: dict, sources: dict[str, str]) -> str | None:
    """A period generated from an entity_type-tagged polity that was
    promoted to timeline_role: period (id convention "<polity_id>_period",
    from classify_period_roles.py's write_period) is itself eligible for the
    Civilizations & Cultures lane, even when its canonical_name doesn't
    literally contain "civilization"/"culture" -- it's usually just a plain
    copy of the polity's name (e.g. "Ancient Egypt"). `sources` is built by
    build.load_civilization_period_role_sources(), since those source
    polities are excluded from build_explore_tree's own `polities` argument
    (load_all() drops timeline_role: period records before this function
    ever sees them)."""
    period_id = period.get("id", "")
    if not period_id.endswith("_period"):
        return None
    return sources.get(period_id[: -len("_period")])


def build_explore_tree(
    polities: list[dict],
    periods: list[dict],
    period_links: list[dict],
    civilization_period_sources: dict[str, str] | None = None,
) -> dict:
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
    civilization_period_sources = civilization_period_sources or {}
    hierarchy = PeriodHierarchy(periods=periods, period_links=period_links, polities=polities)
    periods_by_id = {p["id"]: p for p in periods}
    all_eras = [p for p in periods if p.get("tier") == "regional_era"]

    def _is_civilization_period(p: dict) -> bool:
        return _is_civilization_lane_period(p) or _civilization_period_source_entity_type(p, civilization_period_sources) is not None

    all_periods = [p for p in periods if p.get("tier") == "period" and not _is_civilization_period(p)]
    civilization_periods = [p for p in periods if _is_civilization_period(p)]

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

    for cid in chapter_ids:
        eras_by_chapter[cid] = _merge_auto_generated_eras(eras_by_chapter[cid], chapters_by_id[cid])

    chapter_curated_ids: dict[str, set[str]] = {}
    for cid in chapter_ids:
        curated_ids: set[str] = set()
        for era_entry in eras_by_chapter[cid]:
            for period_entry in era_entry["periods"]:
                curated_ids.update(entities_by_period.get(period_entry["id"], []))
        chapter_curated_ids[cid] = curated_ids
    all_curated_ids: set[str] = set().union(*chapter_curated_ids.values()) if chapter_curated_ids else set()

    # Civilizations & Cultures lane: entity_type-tagged polities and
    # name-matched civilization periods, placed per chapter by date overlap
    # alone (no era/region nesting -- the lane is a single flat row, since
    # per-chapter counts are small). Computed before Pass 2 so its polities
    # can be excluded from the ordinary polities-by-region/continent buckets.
    civilizations_by_chapter: dict[str, list[dict]] = {cid: [] for cid in chapter_ids}
    all_chapters = [chapters_by_id[c] for c in chapter_ids]
    for period in civilization_periods:
        best = _best_chapter_for_range((period["start"], period["end"]), all_chapters)
        if best is not None:
            source_entity_type = _civilization_period_source_entity_type(period, civilization_period_sources)
            civilizations_by_chapter[best["id"]].append(_civilization_period_entry(period, source_entity_type))
    for polity in polities:
        if polity.get("entity_type") not in CIVILIZATION_ENTITY_TYPES or not in_scope(polity):
            continue
        best = best_chapter_for_polity(polity, all_chapters, open_end)
        if best is not None:
            civilizations_by_chapter[best["id"]].append(_civilization_polity_entry(polity))
    for cid in chapter_ids:
        civilizations_by_chapter[cid].sort(key=lambda e: (e["start"], e["id"]))

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
            if polity.get("entity_type") in CIVILIZATION_ENTITY_TYPES:
                continue  # handled by the Civilizations & Cultures lane above, not the Polities row
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
            "civilizations": civilizations_by_chapter[cid],
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
    """Build a JSON-serializable dict entry for a regional-era node in the
    explore tree. `auto_generated` flags placeholder eras created by
    generate_modern_regional_eras.py (one per continent x modern chapter,
    no real historical distinction) so the display tree can merge them --
    see build_explore_tree's era-merge step. `primary_continent` lets the
    /explore era row group by continent. `primary_historical_region` lets
    the /explore era row further split the Asia continent bucket into
    finer regional sub-buckets (East Asia, West Asia, etc.)."""
    geo = era.get("geography") or {}
    return {
        "id": era["id"],
        "canonical_name": era["canonical_name"],
        "start": era["start"],
        "end": era["end"],
        "periods": periods_out,
        "auto_generated": era.get("authority") == AUTO_GENERATED_AUTHORITY,
        "primary_continent": geo.get("primary_continent") or (geo.get("continents") or [None])[0] or "unclassified",
        "primary_historical_region": geo.get("primary_historical_region") or (geo.get("historical_regions") or [None])[0] or "unclassified",
    }


def _merge_auto_generated_eras(eras: list[dict], chapter: dict) -> list[dict]:
    """Collapse a chapter's auto-generated continent-split eras (all share
    the chapter's own date range, one per continent, no real historical
    distinction beyond geography -- see generate_modern_regional_eras.py)
    into a single combined display row, so the era row doesn't show up to
    7 visually redundant near-duplicate bands for one chapter. Only
    reshapes the display tree, after period placement has already
    happened -- the underlying periods/*.yaml era records and
    geography-based period placement (rank_candidates) are untouched."""
    auto = [e for e in eras if e["auto_generated"]]
    curated = [e for e in eras if not e["auto_generated"]]
    if len(auto) <= 1:
        return eras
    merged = {
        "id": f"{chapter['id']}_by_continent_era",
        "canonical_name": f"{chapter['canonical_name']} (by continent)",
        "start": chapter["start"],
        "end": chapter["end"],
        "periods": [period for era in auto for period in era["periods"]],
        "auto_generated": True,
    }
    return curated + [merged]


def _period_entry(period: dict, curated: bool) -> dict:
    """Build a JSON-serializable dict entry for a named-period node with its
    curated/heuristic flag. `primary_continent` lets the /explore period row
    group by continent. `primary_historical_region` lets the /explore period
    row further split the Asia continent bucket into finer regional
    sub-buckets (East Asia, West Asia, etc.)."""
    geo = period.get("geography") or {}
    return {
        "id": period["id"],
        "canonical_name": period["canonical_name"],
        "start": period["start"],
        "end": period["end"],
        "curated": curated,
        "primary_continent": geo.get("primary_continent") or (geo.get("continents") or [None])[0] or "unclassified",
        "primary_historical_region": geo.get("primary_historical_region") or (geo.get("historical_regions") or [None])[0] or "unclassified",
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


def _civilization_polity_entry(polity: dict) -> dict:
    """Build a JSON-serializable dict entry for a civilization/culture/
    people/tribe-typed polity in the Civilizations & Cultures lane.
    `curated` is always True -- entity_type is a reviewed field, not a
    heuristic guess, unlike the name-matched periods alongside it."""
    return {
        "id": polity["id"],
        "canonical_name": polity["canonical_name"],
        "start": polity["start"],
        "end": polity.get("end"),
        "curated": True,
        "source": "polity",
        "entity_type": polity.get("entity_type"),
    }


def _civilization_period_entry(period: dict, source_entity_type: str | None = None) -> dict:
    """Build a JSON-serializable dict entry for a civilization period in the
    Civilizations & Cultures lane. `curated` reflects how it got here: True
    when `source_entity_type` is set (a real, reviewed Polity.entity_type
    field, via a promoted timeline_role: period companion record) or the
    period itself carries CIVILIZATION_BACKDROP_AUTHORITY (also a real,
    deliberate signal) -- False when it's only a canonical_name substring
    match (_is_civilization_lane_period's name heuristic) -- a guess, not a
    classification."""
    curated = source_entity_type is not None or period.get("authority") == CIVILIZATION_BACKDROP_AUTHORITY
    entry = {
        "id": period["id"],
        "canonical_name": period["canonical_name"],
        "start": period["start"],
        "end": period["end"],
        "curated": curated,
        "source": "period",
    }
    if source_entity_type is not None:
        entry["entity_type"] = source_entity_type
    return entry
