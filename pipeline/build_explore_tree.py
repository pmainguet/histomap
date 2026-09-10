"""Build-time step: precompute explore_tree.json, the full period hierarchy
(macro chapter -> regional era -> named period, plus polities bucketed per
chapter by historical region and by continent, plus a flat Civilizations &
Cultures lane and a flat Micronations lane per chapter) that /explore
renders directly. Retires build_explore_index.py's flatter top-N summary --
the new hierarchical /explore view needs the whole tree, not just each
chapter's top 3 entities. See docs/plans/2026-08-30-explore-hierarchy-timeline.md."""

from __future__ import annotations

from pipeline.geography_overlap import overlap_years
from pipeline.period_hierarchy import PeriodHierarchy
from pipeline.suggest_regional_eras import rank_candidates

AUTO_GENERATED_AUTHORITY = "Histomap editorial: auto-generated continent x chapter node"


def _attach_nested_details(details_by_target: dict[str, list[dict]]) -> None:
    """Multi-level detail_of chains are real data (ROADMAP.md item 0): an
    entity can itself be a detail_of another entity's detail (e.g. Kingdom
    of Castile -> Crown of Castile -> Hispanic Monarchy). Recursively
    attaches each detail's own details_by_target entry (if any) onto its
    own dict, so /explore's renderer can walk the nesting to any depth --
    the rest of this module only ever attaches details_by_target[polity_id]
    once, at the top-level entry (see build_explore_tree below)."""
    def attach(detail: dict, seen: frozenset[str]) -> None:
        detail_id = detail["id"]
        if detail_id in seen:
            return  # defensive: build.py's validate_entity_relationships()
                     # already rejects detail_of cycles, but never recurse
                     # forever if one somehow slips through.
        nested = details_by_target.get(detail_id)
        if not nested:
            return
        for child in nested:
            attach(child, seen | {detail_id})
        detail["details"] = nested

    for details in details_by_target.values():
        for detail in details:
            attach(detail, frozenset())

# Polity.entity_type values that mean "not really a weight-bearing political
# entity" -- these render in the Civilizations & Cultures lane instead of the
# Polities row. `tribe` was here too until 10 September 2026 -- moved back to
# the ordinary Polities row on request (a tribe is treated as any other
# weight-bearing polity for /explore's purposes, unlike civilization/culture/
# people, which stay backdrop-only).
CIVILIZATION_ENTITY_TYPES = {"civilization", "culture", "people"}

# Polity.entity_type value for self-declared joke/novelty polities (Hubbistan,
# the Republic of Rose Island, ...) -- like CIVILIZATION_ENTITY_TYPES, these
# render in their own lane (Micronations) instead of the ordinary Polities
# row, so they don't crowd out real states in the default view. Added 10
# September 2026 per explicit request ("move all micronations to a separate
# lane ... hidden by default").
MICRONATION_ENTITY_TYPES = {"micronation"}

# Both lanes above are excluded from the ordinary Polities row and from its
# "no curated placement" heuristic precompute -- combined here so those two
# exclusion checks read as one condition instead of two ORed constants.
NON_POLITY_ROW_ENTITY_TYPES = CIVILIZATION_ENTITY_TYPES | MICRONATION_ENTITY_TYPES


def primary_geography(geo: dict, primary_key: str, list_key: str) -> str:
    """The explicit primary value of a geography facet, else its first listed
    value, else "unclassified". Every /explore node carries both facets
    (continent and historical region) resolved this way, so the front end can
    group by either without re-deriving the fallback."""
    return geo.get(primary_key) or (geo.get(list_key) or [None])[0] or "unclassified"


def primary_continent(geo: dict) -> str:
    return primary_geography(geo, "primary_continent", "continents")


def primary_historical_region(geo: dict) -> str:
    return primary_geography(geo, "primary_historical_region", "historical_regions")


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


def _is_epoch_lane_period(period: dict) -> bool:
    """A tier=period record that belongs in the top-level Epoch lane --
    e.g. Holocene -- rather than the plain Period row (chapter/era-nested)
    or the Civilizations & Cultures lane. Explicit, curator-set field only
    (schema.Period.epoch_lane), no name-heuristic fallback: unlike
    civilization_lane, there's no pre-existing corpus of un-flagged epoch
    records to backfill a guess for. Found live, 8 September 2026 --
    Holocene needed the same click/zoom/detail_of support every other
    entity gets, which the old static geological_epochs.js band (still
    used for finer geological stages with no Histomap record of their own)
    never had."""
    return period.get("tier") == "period" and bool(period.get("epoch_lane"))


def _epoch_entry(period: dict) -> dict:
    """Build a JSON-serializable dict entry for the top-level Epoch lane --
    simpler than _period_entry: no era/chapter nesting (curated/era_id
    don't apply), no geography-based grouping (the lane is a single flat
    global row, like Era)."""
    return {
        "id": period["id"],
        "canonical_name": period["canonical_name"],
        "start": period["start"],
        "end": period["end"],
    }


def _is_civilization_lane_period(period: dict) -> bool:
    """A tier=period record that belongs in the Civilizations & Cultures
    lane rather than the plain Period row. `civilization_lane` (explicit,
    curator-editable, see schema.Period.civilization_lane) is checked first
    when set -- an explicit human decision beats both of the old fallback
    signals. Only when it's unset (None, "not yet reviewed") does this fall
    back to those: either the period carries CIVILIZATION_BACKDROP_AUTHORITY
    (a real signal), or its canonical_name suggests civilization/culture --
    e.g. "Minoan civilization", "Etruscan civilization" (a name-pattern
    heuristic/guess, since Period had no entity_type-like field of its own
    before this field existed). tier=period only -- never regional_era/
    macro_chapter, which are structural grouping nodes, not entities."""
    if period.get("tier") != "period":
        return False
    explicit = period.get("civilization_lane")
    if explicit is not None:
        return explicit
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
    events: list[dict] | None = None,
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
    events = events or []
    hierarchy = PeriodHierarchy(periods=periods, period_links=period_links, polities=polities)
    periods_by_id = {p["id"]: p for p in periods}
    all_eras = [p for p in periods if p.get("tier") == "regional_era"]

    def _is_civilization_period(p: dict) -> bool:
        return _is_civilization_lane_period(p) or _civilization_period_source_entity_type(p, civilization_period_sources) is not None

    epoch_periods = [p for p in periods if _is_epoch_lane_period(p)]
    all_periods = [
        p for p in periods
        if p.get("tier") == "period" and not _is_civilization_period(p) and not _is_epoch_lane_period(p)
    ]
    civilization_periods = [p for p in periods if _is_civilization_period(p)]

    entities_by_period: dict[str, list[str]] = {}
    for link in period_links:
        entities_by_period.setdefault(link["period_id"], []).append(link["entity_id"])

    chapter_ids = hierarchy.macro_chapters()
    chapters_by_id = {cid: periods_by_id[cid] for cid in chapter_ids}
    open_end = max(chapters_by_id[cid]["end"] for cid in chapter_ids)

    # A detail_of entity (see ROADMAP.md item 0 / docs/plans/2026-09-01-detail-of-merge-design.md)
    # never gets its own independent top-level entry -- it's grouped under
    # its container's own entry instead (`details`, attached below), which
    # /explore reveals via a badge/zoom-triggered panel rather than showing
    # by default. Periods can carry detail_of too (e.g. Initial Jomon ->
    # Jomon period), targeting either another period or a polity -- the
    # reverse is never possible (see build.py's validate_entity_relationships/
    # validate_period_detail_of), so this single unified map covers both
    # entity kinds, each detail dict carrying its own `kind` so /explore
    # knows which zoom-target type to use. Built once here, before Pass 1
    # (period placement) and Pass 2 (polity bucketing) both need it -- a
    # detail's dates/geography don't need to match its container's own
    # placement, since it shows wherever the container itself lands.
    details_by_target: dict[str, list[dict]] = {}
    for polity in polities:
        target_id = polity.get("detail_of")
        if not target_id:
            continue
        details_by_target.setdefault(target_id, []).append({
            "id": polity["id"],
            "canonical_name": polity.get("canonical_name", polity["id"]),
            "start": polity.get("start"),
            "end": polity.get("end"),
            "kind": "polity",
        })
    for period in all_periods:
        target_id = period.get("detail_of")
        if not target_id:
            continue
        details_by_target.setdefault(target_id, []).append({
            "id": period["id"],
            "canonical_name": period.get("canonical_name", period["id"]),
            "start": period.get("start"),
            "end": period.get("end"),
            "kind": "period",
        })
    # ROADMAP.md item 5 / docs/plans/2026-09-07-events-lane-design.md: an
    # event's detail_of is a list (an event can be a detail of several
    # entities at once, unlike a polity/period's single detail_of), and it
    # has no start/end -- a single `year` stands in for both, so it nests
    # and sorts the same way a zero-length band would.
    for event in events:
        for target_id in event.get("detail_of") or []:
            details_by_target.setdefault(target_id, []).append({
                "id": event["id"],
                "canonical_name": event.get("canonical_name", event["id"]),
                "start": event.get("year"),
                "end": event.get("year"),
                "kind": "event",
            })
        # ROADMAP.md item 0 (8 September 2026): an event's bounds (the
        # era/chapter/period it starts or ends) used to only ever appear on
        # /explore via its own Events-lane marker -- clicking the period
        # it's actually bound to showed nothing, unlike every other
        # detail_of relationship. Same detail shape as above; a bound
        # event can attach to several periods (edge=start on one,
        # edge=end on another) same as detail_of's own multi-target list.
        for bound in event.get("bounds") or []:
            target_id = bound.get("target")
            if not target_id:
                continue
            details_by_target.setdefault(target_id, []).append({
                "id": event["id"],
                "canonical_name": event.get("canonical_name", event["id"]),
                "start": event.get("year"),
                "end": event.get("year"),
                "kind": "event",
            })
    for details in details_by_target.values():
        details.sort(key=lambda d: (d["start"] if d["start"] is not None else 0, d["id"]))
    _attach_nested_details(details_by_target)

    # Top-level Epoch lane -- a single flat global row, like Era, not nested
    # under any chapter (an epoch like Holocene spans several chapters at
    # once, so there's no one chapter to place it under). detail_of children
    # (e.g. Holocene's Greenlandian/Northgrippian/Meghalayan stages) attach
    # via the same details_by_target map every other row already uses.
    epochs_out = []
    for period in sorted(epoch_periods, key=lambda p: (p["start"], p["id"])):
        entry = _epoch_entry(period)
        if period["id"] in details_by_target:
            entry["details"] = details_by_target[period["id"]]
        epochs_out.append(entry)

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
        if period.get("detail_of"):
            continue  # attached to its container's entry instead, not shown independently
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
        period_entry = _period_entry(period, curated=curated, era_id=era_entry["id"])
        if period["id"] in details_by_target:
            period_entry["details"] = details_by_target[period["id"]]
        era_entry["periods"].append(period_entry)
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
        best = chapters_by_id.get(period.get("linked_chapter_id")) or _best_chapter_for_range(
            (period["start"], period["end"]), all_chapters
        )
        if best is not None:
            source_entity_type = _civilization_period_source_entity_type(period, civilization_period_sources)
            civilizations_by_chapter[best["id"]].append(_civilization_period_entry(period, source_entity_type))
    for polity in polities:
        if polity.get("entity_type") not in CIVILIZATION_ENTITY_TYPES:
            continue
        best = chapters_by_id.get(polity.get("linked_chapter_id")) or best_chapter_for_polity(
            polity, all_chapters, open_end
        )
        if best is not None:
            civilizations_by_chapter[best["id"]].append(_civilization_polity_entry(polity))
    for cid in chapter_ids:
        civilizations_by_chapter[cid].sort(key=lambda e: (e["start"], e["id"]))

    # Micronations lane: entity_type: micronation polities, placed the same
    # way as the Civilizations & Cultures lane above (date overlap, single
    # flat row per chapter) but hidden by default on the front end -- see
    # ROADMAP.md's "move all micronations to a separate lane" item. Unlike
    # the Civilizations & Cultures loop above, a detail_of'd micronation
    # (e.g. the Most Serene Federal Republic of Montmartre, detail_of the
    # Republic of Montmartre) is skipped here and surfaces instead under its
    # container's own `details` list, same as every detail_of entity
    # elsewhere in this tree.
    micronations_by_chapter: dict[str, list[dict]] = {cid: [] for cid in chapter_ids}
    for polity in polities:
        if polity.get("entity_type") not in MICRONATION_ENTITY_TYPES:
            continue
        if polity.get("detail_of"):
            continue
        best = chapters_by_id.get(polity.get("linked_chapter_id")) or best_chapter_for_polity(
            polity, all_chapters, open_end
        )
        if best is not None:
            entry = _civilization_polity_entry(polity)
            if polity["id"] in details_by_target:
                entry["details"] = details_by_target[polity["id"]]
            micronations_by_chapter[best["id"]].append(entry)
    for cid in chapter_ids:
        micronations_by_chapter[cid].sort(key=lambda e: (e["start"], e["id"]))

    # The "no curated placement" heuristic below doesn't depend on which chapter
    # is currently being assembled, so it's computed once per polity here rather
    # than once per (chapter, polity) pair inside Pass 2's per-chapter loop.
    best_chapter_by_polity_id: dict[str, dict | None] = {}
    for polity in polities:
        if polity.get("entity_type") in NON_POLITY_ROW_ENTITY_TYPES:
            continue
        if polity.get("detail_of"):
            continue
        polity_id = polity["id"]
        linked_chapter_id = polity.get("linked_chapter_id")
        if linked_chapter_id and linked_chapter_id in chapters_by_id:
            continue  # explicit human link, heuristic never consulted
        if polity_id in all_curated_ids:
            continue  # curated under some chapter already
        best_chapter_by_polity_id[polity_id] = best_chapter_for_polity(polity, all_chapters, open_end)

    # Pass 2: bucket polities per chapter by region, using the curated ids
    # from Pass 1.
    chapters_out = []
    for cid in chapter_ids:
        chapter = chapters_by_id[cid]
        by_region: dict[str, list[dict]] = {}
        by_continent: dict[str, list[dict]] = {}
        for polity in polities:
            if polity.get("entity_type") in NON_POLITY_ROW_ENTITY_TYPES:
                continue  # handled by the Civilizations & Cultures or Micronations lane above, not the Polities row
            if polity.get("detail_of"):
                continue  # attached to its container's entry below, not shown independently
            polity_id = polity["id"]
            linked_chapter_id = polity.get("linked_chapter_id")
            # A stale/mistyped id (no longer a real chapter) falls through to the
            # normal logic below rather than silently vanishing the polity from
            # every chapter -- only a *valid* explicit id short-circuits it.
            if linked_chapter_id and linked_chapter_id in chapters_by_id:
                # An explicit human decision beats both the period_links.yaml-curated
                # path and the heuristic -- it's the strongest signal there is.
                if linked_chapter_id != cid:
                    continue
                is_curated = True
            else:
                is_curated = polity_id in chapter_curated_ids[cid]
                if not is_curated:
                    if polity_id in all_curated_ids:
                        continue  # curated under a *different* chapter
                    best = best_chapter_by_polity_id.get(polity_id)
                    if best is None or best["id"] != cid:
                        continue
            geo = polity.get("geography") or {}
            region = primary_historical_region(geo)
            continent = primary_continent(geo)
            entry = _polity_entry(polity, curated=is_curated)
            if polity_id in details_by_target:
                entry["details"] = details_by_target[polity_id]
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
            "micronations": micronations_by_chapter[cid],
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
        "epochs": epochs_out,
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
        "primary_continent": primary_continent(geo),
        "primary_historical_region": primary_historical_region(geo),
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


def _geo_fields(geo: dict) -> dict:
    """The primary_continent/primary_historical_region/present_countries triple
    every explore-tree entry builder below derives from a record's `geography`
    the same way, so /explore's period, polity, and civilization rows can share
    one client-side geography-grouping implementation instead of several."""
    return {
        "primary_continent": primary_continent(geo),
        "primary_historical_region": primary_historical_region(geo),
        "present_countries": geo.get("present_countries") or [],
    }


def _period_entry(period: dict, curated: bool, era_id: str) -> dict:
    """Build a JSON-serializable dict entry for a named-period node with its
    curated/heuristic flag. `primary_continent` lets the /explore period row
    group by continent. `primary_historical_region` lets the /explore period
    row further split the Asia continent bucket into finer regional
    sub-buckets (East Asia, West Asia, etc.). `present_countries` lets the
    period row further sub-group each continent bucket by country (e.g.
    Jomon and Yayoi both cluster under Japan within the East Asia bucket).
    `era_id` is the id of the regional_era this period is actually nested
    under in the tree (known for free at the call site) -- /explore uses it
    to color the period band to match its era's band, so e.g. every period
    under Mesopotamian Early States reads as one visual group."""
    geo = period.get("geography") or {}
    return {
        "id": period["id"],
        "canonical_name": period["canonical_name"],
        "start": period["start"],
        "end": period["end"],
        "curated": curated,
        "era_id": era_id,
        **_geo_fields(geo),
    }


def _polity_entry(polity: dict, curated: bool) -> dict:
    """Build a JSON-serializable dict entry for a polity with its curated/heuristic flag.
    `primary_continent`/`primary_historical_region` mirror era/period entries' own
    fields (same fallback logic) so the /explore period and polities rows can share
    one client-side geography-grouping implementation instead of two -- polities were
    previously only bucketed server-side (`polities_by_continent`/
    `polities_by_historical_region`), which couldn't be reused for the period row's
    client-side Asia-split logic. `linked_era_id` is a plain, curator-editable field
    (see schema.Polity.linked_era_id) -- not computed here -- used for /explore's
    era-matched band coloring."""
    geo = polity.get("geography") or {}
    return {
        "id": polity["id"],
        "canonical_name": polity["canonical_name"],
        "start": polity["start"],
        "end": polity.get("end"),
        "curated": curated,
        "linked_era_id": polity.get("linked_era_id"),
        **_geo_fields(geo),
    }


def _civilization_polity_entry(polity: dict) -> dict:
    """Build a JSON-serializable dict entry for a civilization/culture/
    people-typed polity in the Civilizations & Cultures lane. Also reused
    as-is for the Micronations lane (see MICRONATION_ENTITY_TYPES) -- the
    shape only depends on generic polity fields, not on which of the two
    lanes it ends up in; `entity_type` on the resulting entry distinguishes
    them for the front end. `curated` is always True -- entity_type is a
    reviewed field, not a heuristic guess, unlike the name-matched periods
    alongside it.
    `primary_continent`/`primary_historical_region`/`present_countries`
    mirror _period_entry/_polity_entry's own fields so this lane can share
    the same client-side continent/country grouping. `linked_era_id` is a
    plain, curator-editable field (see schema.Polity.linked_era_id), not
    computed here -- used only for era-matched color coding, not for
    grouping/placement. Was heuristically computed (date+geography overlap)
    until 2026-08-31; that heuristic seeded the field's initial values but
    no longer runs -- see ROADMAP.md's "heuristic/on-the-fly computation
    audit" item for the same question applied to other fields."""
    geo = polity.get("geography") or {}
    return {
        "id": polity["id"],
        "canonical_name": polity["canonical_name"],
        "start": polity["start"],
        "end": polity.get("end"),
        "curated": True,
        "source": "polity",
        "entity_type": polity.get("entity_type"),
        "linked_era_id": polity.get("linked_era_id"),
        **_geo_fields(geo),
    }


def _civilization_period_entry(period: dict, source_entity_type: str | None = None) -> dict:
    """Build a JSON-serializable dict entry for a civilization period in the
    Civilizations & Cultures lane. `curated` reflects how it got here: True
    when `source_entity_type` is set (a real, reviewed Polity.entity_type
    field, via a promoted timeline_role: period companion record) or the
    period itself carries CIVILIZATION_BACKDROP_AUTHORITY (also a real,
    deliberate signal) -- False when it's only a canonical_name substring
    match (_is_civilization_lane_period's name heuristic) -- a guess, not a
    classification. See _civilization_polity_entry for the geography/
    linked_era_id fields shared with the polity-sourced entries."""
    curated = source_entity_type is not None or period.get("authority") == CIVILIZATION_BACKDROP_AUTHORITY
    geo = period.get("geography") or {}
    entry = {
        "id": period["id"],
        "canonical_name": period["canonical_name"],
        "start": period["start"],
        "end": period["end"],
        "curated": curated,
        "source": "period",
        "linked_era_id": period.get("linked_era_id"),
        **_geo_fields(geo),
    }
    if source_entity_type is not None:
        entry["entity_type"] = source_entity_type
    return entry
