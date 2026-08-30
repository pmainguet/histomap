# Explore Hierarchy Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `/explore`'s 9-tile grid (which hands off to the flat, single-dropdown `/` timeline) with a single page that renders the period hierarchy directly — geological epoch, macro chapter, regional era, and named period as stacked bands sharing one time axis, plus a polities band the user can group by historical region, by present-day continent, or hide.

**Architecture:** A new build step (`pipeline/build_explore_tree.py`) precomputes the full nested tree — chapters → eras → periods, plus polities bucketed per chapter by region — into `explore_tree.json`, served as a static file exactly like `periods.json` today. `/explore` becomes a purpose-built renderer (`web/explore_timeline.js`) built from two small, dependency-free JS modules (a broken-axis linear scale, and a greedy interval-lane packer) that read `explore_tree.json` directly. `app.js`'s existing SVG timeline is not modified — it already works, has no test coverage to protect a refactor, and needs a different (two-level, geography+relationship) lane model than this hierarchy view needs (region-only). Where the curated tree (`broader_periods` / `period_links.yaml`) has no entry for a node, placement falls back to the same geography+date overlap heuristic the suggestion queues already use, so the view is populated today instead of showing "0 entities" everywhere — heuristic placements render with a visibly different treatment and are never written back into curated data.

**Tech Stack:** Python (pipeline, matches existing `pipeline/*.py` conventions), vanilla JS (matches `web/*.js`, no framework, no build step, no new dependencies), `unittest` for Python tests (no JS test harness exists in this repo — JS tasks are verified manually in a browser, matching how `app.js`/`explore.js` are verified today).

**Spec:** [ONTOLOGY.md](../../ONTOLOGY.md) — in particular "Tree, lanes, graph" (the tree/lanes/graph split this plan implements) and "How a future timeline UI should read this" (the `PeriodHierarchy` query contract this plan is the "future timeline UI" for).

## Global Constraints

- No new Python dependencies — stdlib + existing `pyyaml`/`pydantic`/`fastapi` only.
- No new JS dependencies — vanilla JS only, no CDN scripts, no framework (the app must keep working fully offline via `python -m server.app`).
- Curated data (`period_links.yaml`, `Period.broader_periods`) is never auto-written by this feature. Heuristic placement is display-only and lives entirely inside `explore_tree.json`.
- Query the tree through `pipeline/period_hierarchy.py`'s `PeriodHierarchy`, not by re-deriving `broader_periods`/`period_links.yaml` traversal — per ONTOLOGY.md's explicit instruction to future UI work.
- The broken time-axis segment break is read from data (`min(start for macro chapters)`'s sibling chapter boundary — concretely, the end year of the earliest macro chapter) — never hardcoded as a literal year, since chapter boundaries are editorial and can change.
- Reuse the existing palette tokens already defined in `web/styles.css` (`--paper: #f9f5ea`, `--rule: #c7beaa`, ink `#27251f`, `--ink-faint: #777063`, accent `#8c422d`, Georgia serif for headings, `system-ui, sans-serif` for UI chrome) — do not introduce a second palette.
- `unittest`, not `pytest`, for every new Python test file — matches every existing test file in `tests/`.
- Type hints and docstrings on every new/modified Python function (user preference, applies repo-wide).
- Macro chapters are mutually exclusive and contiguous in time by construction (confirmed: the 9 chapters tile `-3,000,000` → `2100` with no gaps or overlaps) — chapter-level placement is a pure date-overlap test, no geography needed. Regional eras are **not** mutually exclusive in time (multiple eras can share a date range in different regions) — era/period-level placement needs geography, not just dates.

---

## Background: why the current `/explore` doesn't work as-is

- All 9 chapter tiles show "0 entities" today: `explore_index.json`'s `top_entities` comes from `PeriodHierarchy.entities_under()`, which only counts polities reachable via curated `period_links.yaml` entries (102 total) — nowhere near enough coverage to populate a page.
- The "Historical period" dropdown on `/` (`web/app.js`'s `periodInput`) is a flat, alphabetically-sorted list of all 174 `periods.json` records — macro chapters, regional eras, and named periods interleaved with no indication of which nests under which. That's the concrete UX bug this plan fixes: the tree exists in the data (`tier` + `broader_periods`) but nowhere in any UI.
- Chapter-level data is fully populated (9/9), regional-era→chapter linkage is fully populated (48/48 regional eras have `broader_periods` set), but period→era linkage is not (0/117 tier=`period` records have `broader_periods` set) and polity→period linkage is sparse (102 `period_links.yaml` entries against thousands of in-scope polities). Rows 3 (named period) and 4 (polities) would render almost empty without a fallback — hence the heuristic placement in Task 1.

---

## Task 1: `explore_tree.json` build step

**Files:**
- Create: `pipeline/geography_overlap.py`
- Modify: `pipeline/suggest_period_links.py`
- Modify: `pipeline/suggest_regional_eras.py`
- Create: `pipeline/build_explore_tree.py`
- Delete: `pipeline/build_explore_index.py`
- Modify: `build.py:18,305-314`
- Modify: `server/app.py:924-929`
- Modify: `Makefile` (if it references `explore_index.json` by name — check with `grep -n explore Makefile`; none was found at plan-writing time, so this may be a no-op)
- Create: `tests/test_geography_overlap.py`
- Create: `tests/test_build_explore_tree.py`
- Delete: `tests/test_build_explore_index.py`
- Modify: `tests/test_suggest_period_links.py` (import path only)
- Modify: `tests/test_suggest_regional_eras.py` (import path only)

**Interfaces:**
- Produces: `pipeline.geography_overlap.geography_matches(source_geo: dict, candidate_geo: dict) -> bool` and `pipeline.geography_overlap.overlap_years(a: tuple[int, int], b: tuple[int, int]) -> int` — the canonical implementations; `suggest_period_links.py` and `suggest_regional_eras.py` re-export them (`from pipeline.geography_overlap import geography_matches, overlap_years`) so their existing public API and existing tests (which import `geography_matches` from each module directly) keep working unchanged.
- Produces: `pipeline.build_explore_tree.build_explore_tree(polities: list[dict], periods: list[dict], period_links: list[dict]) -> dict` — the full tree, shape defined in Step 3 below. Consumed by `build.py` and by `web/explore_timeline.js` (as JSON).
- Consumes: `pipeline.period_hierarchy.PeriodHierarchy` (`macro_chapters()`, `children()`, `entities_under()`) — already exists, unchanged.
- Consumes: `pipeline.suggest_regional_eras.rank_candidates(period: dict, candidates: list[dict]) -> list[dict]` — already exists, unchanged, reused as-is for period→era heuristic placement.

### Step 1: Extract the shared geography-overlap module

`suggest_period_links.py` and `suggest_regional_eras.py` currently each define an identical `geography_matches` function (confirmed byte-for-byte identical logic, only the docstring differs). Extract it once so `build_explore_tree.py` doesn't become a third copy.

Create `pipeline/geography_overlap.py`:

```python
"""Shared geography- and date-overlap helpers used by the suggestion queues
(suggest_period_links.py, suggest_regional_eras.py) and by
build_explore_tree.py. Historical_region overlap (finer-grained, ~23 regions)
is preferred over continent overlap (7 regions) when both sides have
historical_regions set -- continent-only matching produces low-quality
matches for broad continents (e.g. an Iraqi caliphate matching a Chinese
empire purely because both share the "asia" tag). Falls back to continent
overlap when either side lacks historical_regions -- most of the dataset
still does."""

from __future__ import annotations


def overlap_years(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Years of overlap between two [start, end) ranges; 0 if disjoint or touching."""
    lo = max(a[0], b[0])
    hi = min(a[1], b[1])
    return max(0, hi - lo)


def geography_matches(source_geo: dict, candidate_geo: dict) -> bool:
    """Historical_region overlap when both sides have it (tighter, preferred);
    continent overlap otherwise. An empty candidate continents list means
    deliberately global (a macro chapter) -- always eligible; see ONTOLOGY.md's
    tier-scoped geography-emptiness rule."""
    candidate_continents = set(candidate_geo.get("continents") or [])
    if not candidate_continents:
        return True
    source_regions = set(source_geo.get("historical_regions") or [])
    candidate_regions = set(candidate_geo.get("historical_regions") or [])
    if source_regions and candidate_regions:
        return bool(source_regions & candidate_regions)
    source_continents = set(source_geo.get("continents") or [])
    return bool(source_continents & candidate_continents)
```

- [ ] Write `tests/test_geography_overlap.py` by moving the `GeographyMatchesTests` class bodies (not the imports) out of `tests/test_suggest_period_links.py` and `tests/test_suggest_regional_eras.py` into this new file, importing from `pipeline.geography_overlap`, plus these two for `overlap_years`:

```python
import unittest

from pipeline.geography_overlap import geography_matches, overlap_years


class OverlapYearsTests(unittest.TestCase):
    def test_full_containment(self) -> None:
        self.assertEqual(overlap_years((500, 600), (0, 1000)), 100)

    def test_no_overlap_returns_zero(self) -> None:
        self.assertEqual(overlap_years((0, 100), (200, 300)), 0)


class GeographyMatchesTests(unittest.TestCase):
    def test_historical_region_overlap_wins_over_shared_continent(self) -> None:
        source = {"continents": ["asia"], "historical_regions": ["west_asia"]}
        candidate = {"continents": ["asia"], "historical_regions": ["east_asia"]}
        self.assertFalse(geography_matches(source, candidate))

    def test_falls_back_to_continent_when_either_side_lacks_regions(self) -> None:
        source = {"continents": ["asia"]}
        candidate = {"continents": ["asia"], "historical_regions": ["east_asia"]}
        self.assertTrue(geography_matches(source, candidate))

    def test_empty_candidate_continents_always_matches(self) -> None:
        source = {"continents": ["asia"], "historical_regions": ["west_asia"]}
        candidate = {"continents": []}
        self.assertTrue(geography_matches(source, candidate))


if __name__ == "__main__":
    unittest.main()
```

- [ ] In `pipeline/suggest_period_links.py`, delete the local `geography_matches` function body (lines 40-55 as read at plan-writing time) and replace with `from pipeline.geography_overlap import geography_matches` near the top imports. Leave `in_scope`, `_overlap`, `best_period_for_polity`, `main`, and everything else untouched.
- [ ] In `pipeline/suggest_regional_eras.py`, delete the local `geography_matches` function body and the local `overlap_years` function body, replace with `from pipeline.geography_overlap import geography_matches, overlap_years` near the top imports. Leave `rank_candidates`, `load_regional_eras`, `main`, and everything else untouched.
- [ ] In `tests/test_suggest_period_links.py`, change the import to `from pipeline.suggest_period_links import best_period_for_polity, in_scope` (drop `geography_matches` — it's re-exported so `from pipeline.suggest_period_links import geography_matches` would still work, but the canonical test now lives in `test_geography_overlap.py`) and delete the `GeographyMatchesTests` class (now duplicated in `test_geography_overlap.py`). Keep `BestPeriodForPolityTests` and `InScopeTests` unchanged.
- [ ] In `tests/test_suggest_regional_eras.py`, change the import to `from pipeline.suggest_regional_eras import rank_candidates` and delete the `GeographyMatchesTests` class and the `OverlapYearsTests` class (both now in `test_geography_overlap.py`). Keep `RankCandidatesTests` unchanged.
- [ ] Run `python -m unittest tests.test_geography_overlap tests.test_suggest_period_links tests.test_suggest_regional_eras -v` — expect all green, same total assertions as before the move (just relocated).
- [ ] Commit: `git add pipeline/geography_overlap.py pipeline/suggest_period_links.py pipeline/suggest_regional_eras.py tests/test_geography_overlap.py tests/test_suggest_period_links.py tests/test_suggest_regional_eras.py && git commit -m "pipeline: extract shared geography_overlap module"`

### Step 2: Chapter-level polity placement helper

Macro chapters are mutually exclusive and contiguous in time, so chapter assignment for a polity that has no curated link is a pure date-overlap pick among the 9 chapters — no geography test needed at this level (chapters are global by construction).

- [ ] Add to `pipeline/build_explore_tree.py` (new file):

```python
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
```

(`overlap_years` imported from `pipeline.geography_overlap`, per Step 1.)

### Step 3: The tree builder

Define the output shape precisely — this is what `web/explore_timeline.js` (Tasks 4-5) renders directly:

```json
{
  "axis": { "domain_start": -3000000, "domain_end": 2100, "segment_break": -10000 },
  "chapters": [
    {
      "id": "macro_early_cities_states",
      "canonical_name": "Early Cities and States",
      "start": -3500,
      "end": -1200,
      "eras": [
        {
          "id": "egyptian_early_states_era",
          "canonical_name": "Egyptian Early States",
          "start": -3100,
          "end": -1070,
          "periods": [
            {
              "id": "egyptian_old_kingdom",
              "canonical_name": "Egyptian Old Kingdom",
              "start": -2686,
              "end": -2181,
              "curated": true
            }
          ]
        }
      ],
      "polities_by_historical_region": {
        "north_africa": [
          { "id": "old_kingdom_of_egypt", "canonical_name": "Old Kingdom of Egypt", "start": -2686, "end": -2181, "curated": true }
        ]
      },
      "polities_by_continent": {
        "africa": [
          { "id": "old_kingdom_of_egypt", "canonical_name": "Old Kingdom of Egypt", "start": -2686, "end": -2181, "curated": true }
        ]
      }
    }
  ]
}
```

Placement rules, in order:

1. **Chapters** (`hierarchy.macro_chapters()`) — always all 9, always included even with empty `eras`/polities maps.
2. **Eras under a chapter** — every `tier="regional_era"` period whose `broader_periods[0]` equals this chapter's id (already 48/48 populated; no heuristic fallback needed or attempted here — if a future regional era ships without `broader_periods` set, it silently won't appear under any chapter, which is correct: an unlinked era isn't part of the curated tree yet).
3. **Periods under an era** — for each `tier="period"` record: if `broader_periods` is set and points at an era present in this tree, place it there with `"curated": true`. Otherwise, call `rank_candidates(period, all_eras)` (from `pipeline.suggest_regional_eras`, reused unchanged) and take the top match, if any, with `"curated": false`. A period with zero era matches is dropped from the tree (not an error — print a count, same convention as the existing suggestion-queue scripts' "unmatched" counters).
4. **Polities per chapter, by region** — for each chapter: `curated_ids = set(hierarchy.entities_under(chapter_id))` (walks eras and periods already linked into this chapter via `period_links.yaml`, `curated: true`). For every other in-scope polity (`pipeline.suggest_period_links.in_scope`, reused unchanged) not already curated under *any* chapter, call `best_chapter_for_polity` (Step 2); if it resolves to this chapter, include it with `"curated": false`. Bucket every included polity into `polities_by_historical_region` by `polity["geography"].get("primary_historical_region")` (fall back to the first entry of `historical_regions`, then `"unclassified"`) and separately into `polities_by_continent` by `primary_continent` (fall back to first of `continents`, then `"unclassified"`) — every polity appears in exactly one bucket per map. Sort each bucket's list by `start` ascending (ties by `id`) — this is also the order the client's greedy lane-packer (Task 3) wants.
5. No caps applied here — a chapter with hundreds of qualifying polities gets hundreds of entries in its bucket. Capping/collapsing for display is a rendering concern (Task 5), not a data concern; capping silently in the data would make the "N entities" count downstream lie.

```python
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
    return {
        "id": era["id"],
        "canonical_name": era["canonical_name"],
        "start": era["start"],
        "end": era["end"],
        "periods": periods_out,
    }


def _period_entry(period: dict, curated: bool) -> dict:
    return {
        "id": period["id"],
        "canonical_name": period["canonical_name"],
        "start": period["start"],
        "end": period["end"],
        "curated": curated,
    }


def _polity_entry(polity: dict, curated: bool) -> dict:
    return {
        "id": polity["id"],
        "canonical_name": polity["canonical_name"],
        "start": polity["start"],
        "end": polity.get("end"),
        "curated": curated,
    }
```

Full file header/imports for `pipeline/build_explore_tree.py`:

```python
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
```

(the two `def best_chapter_for_polity` / `def build_explore_tree` blocks above, plus the three `_*_entry` helpers, go below the imports.)

- [ ] Write `tests/test_build_explore_tree.py`:

```python
import unittest

from pipeline.build_explore_tree import best_chapter_for_polity, build_explore_tree


def chapter(id_: str, start: int, end: int) -> dict:
    return {"id": id_, "tier": "macro_chapter", "canonical_name": id_, "start": start, "end": end, "broader_periods": []}


def era(id_: str, start: int, end: int, chapter_id: str, continents: list[str], regions: list[str] | None = None) -> dict:
    return {
        "id": id_, "tier": "regional_era", "canonical_name": id_, "start": start, "end": end,
        "broader_periods": [chapter_id],
        "geography": {"continents": continents, "historical_regions": regions or []},
    }


def named_period(id_: str, start: int, end: int, broader: list[str] | None = None, continents: list[str] | None = None) -> dict:
    return {
        "id": id_, "tier": "period", "canonical_name": id_, "start": start, "end": end,
        "broader_periods": broader or [],
        "geography": {"continents": continents or [], "historical_regions": []},
    }


def polity(id_: str, start: int, end: int | None, continent: str, region: str | None = None,
           tier: str = "global") -> dict:
    return {
        "id": id_, "canonical_name": id_, "start": start, "end": end,
        "visibility_tier": tier,
        "geography": {
            "primary_continent": continent, "continents": [continent],
            "primary_historical_region": region, "historical_regions": [region] if region else [],
        },
    }


class BestChapterForPolityTests(unittest.TestCase):
    def test_picks_chapter_containing_polity(self) -> None:
        chapters = [chapter("early", -3500, -1200), chapter("classical", -1200, 500)]
        best = best_chapter_for_polity(polity("p1", -2000, -1900, "africa"), chapters)
        self.assertEqual(best["id"], "early")

    def test_returns_none_when_no_overlap(self) -> None:
        chapters = [chapter("early", -3500, -1200)]
        self.assertIsNone(best_chapter_for_polity(polity("p1", 1000, 1100, "africa"), chapters))


class BuildExploreTreeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.periods = [
            chapter("macro_early", -3500, -1200),
            era("egypt_era", -3100, -1070, "macro_early", ["africa"], ["north_africa"]),
            era("meso_era", -3500, -1200, "macro_early", ["asia"], ["west_asia"]),
            named_period("old_kingdom", -2686, -2181, broader=["egypt_era"]),
            named_period("heuristic_period", -3000, -2800, continents=["africa"]),
        ]
        self.period_links = [
            {"period_id": "old_kingdom", "entity_id": "old_kingdom_egypt", "relation": "part_of_periodization"},
        ]
        self.polities = [
            polity("old_kingdom_egypt", -2686, -2181, "africa", "north_africa"),
            polity("unlinked_egyptian", -2500, -2400, "africa", "north_africa"),
            polity("out_of_scope", -2500, -2400, "africa", "north_africa", tier="detailed"),
        ]

    def test_all_nine_chapter_slots_present_even_with_one_chapter_fixture(self) -> None:
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        self.assertEqual([c["id"] for c in tree["chapters"]], ["macro_early"])

    def test_era_nests_under_its_chapter(self) -> None:
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        chapter_out = tree["chapters"][0]
        self.assertEqual({e["id"] for e in chapter_out["eras"]}, {"egypt_era", "meso_era"})

    def test_curated_period_nests_under_its_curated_era(self) -> None:
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        egypt_era = next(e for e in tree["chapters"][0]["eras"] if e["id"] == "egypt_era")
        self.assertEqual([p["id"] for p in egypt_era["periods"]], ["old_kingdom"])
        self.assertTrue(egypt_era["periods"][0]["curated"])

    def test_heuristic_period_nests_under_best_geography_matched_era(self) -> None:
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        egypt_era = next(e for e in tree["chapters"][0]["eras"] if e["id"] == "egypt_era")
        heuristic = [p for p in egypt_era["periods"] if p["id"] == "heuristic_period"]
        self.assertEqual(len(heuristic), 1)
        self.assertFalse(heuristic[0]["curated"])

    def test_curated_polity_bucketed_by_own_geography_and_flagged_curated(self) -> None:
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        region_bucket = tree["chapters"][0]["polities_by_historical_region"]["north_africa"]
        curated_entry = next(e for e in region_bucket if e["id"] == "old_kingdom_egypt")
        self.assertTrue(curated_entry["curated"])

    def test_unlinked_in_scope_polity_placed_heuristically(self) -> None:
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        region_bucket = tree["chapters"][0]["polities_by_historical_region"]["north_africa"]
        heuristic_entry = next(e for e in region_bucket if e["id"] == "unlinked_egyptian")
        self.assertFalse(heuristic_entry["curated"])

    def test_out_of_scope_polity_excluded(self) -> None:
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        region_bucket = tree["chapters"][0]["polities_by_historical_region"]["north_africa"]
        self.assertNotIn("out_of_scope", {e["id"] for e in region_bucket})

    def test_axis_segment_break_is_earliest_chapter_end(self) -> None:
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        self.assertEqual(tree["axis"]["segment_break"], -1200)


if __name__ == "__main__":
    unittest.main()
```

- [ ] Run: `python -m unittest tests.test_build_explore_tree -v` — expect all PASS.
- [ ] Delete `pipeline/build_explore_index.py` and `tests/test_build_explore_index.py`.
- [ ] In `build.py`: rename `EXPLORE_INDEX_OUT_PATH = ROOT / "explore_index.json"` (line 18) to `EXPLORE_TREE_OUT_PATH = ROOT / "explore_tree.json"`; replace lines 305-314 with:

```python
    from pipeline.build_explore_tree import build_explore_tree

    explore_tree = build_explore_tree(
        [p.model_dump(mode="json") for p in published_polities],
        [p.model_dump(mode="json") for p in periods],
        [link.model_dump(mode="json") for link in period_links],
    )
    EXPLORE_TREE_OUT_PATH.write_text(
        json.dumps(explore_tree, indent=2, ensure_ascii=False), encoding="utf-8"
    )
```

- [ ] In `server/app.py`, replace the `/explore_index.json` route (lines 924-929) with:

```python
    @application.get("/explore_tree.json", include_in_schema=False)
    async def explore_tree() -> FileResponse:
        path = root / "explore_tree.json"
        if not path.exists():
            raise HTTPException(404, "Run the build action first")
        return FileResponse(path)
```

- [ ] Check `grep -n explore Makefile` — if it names `explore_index.json` anywhere, update it to `explore_tree.json`; otherwise no change needed (the target likely just depends on `build`, which already runs the whole pipeline).
- [ ] Delete the stale `explore_index.json` file from the repo root if committed (`git rm explore_index.json` if tracked; check `git ls-files explore_index.json` first — it may be `.gitignore`d as a build artifact like `data.json`).
- [ ] Run `python -m build` (or the project's existing build command — check `Makefile`'s `build` target) and verify `explore_tree.json` is written with a `chapters` array of length 9 and a nonzero `polities_by_historical_region`/`polities_by_continent` total across chapters.
- [ ] Run the full suite: `python -m unittest discover -s tests -v` — expect all green.
- [ ] Commit: `git add -A && git commit -m "pipeline: replace explore_index.json with the full explore_tree.json hierarchy"`

---

## Task 2: Broken-axis time scale (`web/timeline_scale.js`)

**Files:**
- Create: `web/timeline_scale.js`

**Interfaces:**
- Produces: `createTimeScale(domainStart, domainEnd, segmentBreak, innerWidth, deepTimeFraction = 0.1) -> { x(year), width(start, end), tickYears(targetCount) }` — consumed by `web/explore_timeline.js` (Task 4).
- Consumes: nothing (pure, no DOM).

A single linear scale across `-3,000,000..2100` makes chapters 2-9 (the 12,300 years after `segmentBreak`, 0.4% of the full span) collapse to sub-pixel slivers — unacceptable for bands that need to be clickable and readable, unlike the existing decorative geological band (`geological_epochs.js`, which explicitly accepts this: "the sub-Pleistocene epochs render as thin slivers by design," because that band is `aria-hidden` and non-interactive). This view's chapter/era/period/polity bands are the primary content, so instead: a **two-segment broken axis** — everything at or before `segmentBreak` (the earliest chapter's end year, e.g. `-10000`) gets a fixed `deepTimeFraction` (default 10%) of the available width, rendered as a single compressed block; everything after gets the remaining 90%, itself linear. This conveniently lines up with the data: chapter 1 (`Human Origins and Paleolithic Worlds`, `-3,000,000` to `-10,000`) is the only chapter in the compressed segment; chapters 2-9 get 90% of the width to themselves, fully linear and readable.

- [ ] Write `web/timeline_scale.js`:

```js
// Two-segment broken linear scale: years at or before `segmentBreak` get a
// small fixed share of the width (deep time is real but visually
// uninformative at true scale -- see docs/plans/2026-08-30-explore-hierarchy-timeline.md
// Task 2); years after get the rest, at a uniform linear rate. Both segments
// are individually linear -- proportions are honest within each segment,
// just not across the break.
function createTimeScale(domainStart, domainEnd, segmentBreak, innerWidth, deepTimeFraction = 0.1) {
  const deepTimeWidth = innerWidth * deepTimeFraction;
  const recentWidth = innerWidth - deepTimeWidth;
  const deepSpan = segmentBreak - domainStart;
  const recentSpan = domainEnd - segmentBreak;

  function x(year) {
    if (year <= segmentBreak) {
      const fraction = deepSpan > 0 ? (year - domainStart) / deepSpan : 0;
      return fraction * deepTimeWidth;
    }
    const fraction = recentSpan > 0 ? (year - segmentBreak) / recentSpan : 0;
    return deepTimeWidth + fraction * recentWidth;
  }

  function width(start, end) {
    const clampedStart = Math.max(domainStart, start);
    const clampedEnd = Math.min(domainEnd, end ?? domainEnd);
    return Math.max(2, x(clampedEnd) - x(clampedStart));
  }

  // "Nice" round-number tick years (1/2/5 x10^n), restricted to the recent
  // segment -- deep-time ticks would be too sparse/large to be useful in a
  // 10%-width block. Mirrors app.js's niceTickStep but returns actual years,
  // not a step, since ticks must respect the segment break.
  function tickYears(targetCount = 8) {
    const rawStep = recentSpan / targetCount;
    const magnitude = 10 ** Math.floor(Math.log10(Math.max(1, rawStep)));
    const candidates = [1, 2, 5, 10].map((m) => m * magnitude);
    const step = candidates.find((c) => recentSpan / c <= targetCount * 1.5) || candidates[candidates.length - 1];
    const ticks = [];
    for (let year = Math.ceil(segmentBreak / step) * step; year <= domainEnd; year += step) {
      ticks.push(year);
    }
    return ticks;
  }

  return { x, width, tickYears, deepTimeWidth, recentWidth };
}
```

- [ ] Manual verification (no JS test harness exists in this repo — every existing `web/*.js` file is verified by hand in a browser; this task follows that convention): create a scratch `web/_scale_check.html` (not committed) that loads `timeline_scale.js` and logs `createTimeScale(-3000000, 2100, -10000, 900)`'s `x(-3000000)` (expect `0`), `x(-10000)` (expect `90`, i.e. `deepTimeWidth`), `x(2100)` (expect `900`), and `x(0)` (expect strictly between `90` and `900`, close to `90` since `0` CE is near the start of the recent segment). Delete the scratch file once confirmed.
- [ ] Commit: `git add web/timeline_scale.js && git commit -m "web: add broken-axis time scale for the Explore hierarchy view"`

---

## Task 3: Greedy interval lane packer (`web/lane_packing.js`)

**Files:**
- Create: `web/lane_packing.js`

**Interfaces:**
- Produces: `packIntoLanes(items) -> Array<Array<item>>` where each inner array is one lane (a list of non-time-overlapping items, in the order they were assigned), consumed by `web/explore_timeline.js` (Tasks 4-5) for the regional-era row, the named-period row, and each region sub-group of the polities row.
- Consumes: items shaped `{ start: number, end: number | null, ... }`, must already be sorted by `start` ascending (Task 1's builder already sorts polity buckets this way; eras/periods within a chapter/era are read in `periods.json`/tree order and should be sorted by the caller before packing).

Regional eras and named periods are not mutually exclusive in time (two eras can share a date range in different regions), so rendering them in a single row needs vertical sub-lanes. Standard greedy interval-graph coloring: sorted by start, place each item in the first lane whose last item has already ended; open a new lane if none fits.

- [ ] Write `web/lane_packing.js`:

```js
// Greedy interval-graph coloring: assigns each item (already sorted by
// start ascending) to the first lane whose last-placed item ends at or
// before this item's start, opening a new lane otherwise. Produces the
// minimum number of lanes needed so that no two items in the same lane
// overlap in time. Used for rows where entries aren't mutually exclusive
// in time (regional eras, named periods, polities within one region).
function packIntoLanes(items) {
  const lanes = [];
  for (const item of items) {
    const itemEnd = item.end ?? Infinity;
    let placed = false;
    for (const lane of lanes) {
      const last = lane[lane.length - 1];
      const lastEnd = last.end ?? Infinity;
      if (lastEnd <= item.start) {
        lane.push(item);
        placed = true;
        break;
      }
    }
    if (!placed) lanes.push([item]);
  }
  return lanes;
}
```

- [ ] Manual verification via the same scratch-HTML approach as Task 2: `packIntoLanes([{start:0,end:10},{start:5,end:15},{start:20,end:30}])` should return 2 lanes: `[[{0,10},{20,30}], [{5,15}]]` (the third item reuses lane 1 since it starts after lane 1's last item ends). Delete the scratch file once confirmed.
- [ ] Commit: `git add web/lane_packing.js && git commit -m "web: add greedy interval lane packer for the Explore hierarchy view"`

---

## Task 4: Hierarchy renderer core (geological + chapter + era + period rows)

**Files:**
- Create: `web/explore_timeline.js`

**Interfaces:**
- Consumes: `createTimeScale` (Task 2), `packIntoLanes` (Task 3), `GEOLOGICAL_EPOCHS` (existing `web/geological_epochs.js`, unchanged), `explore_tree.json` (Task 1's shape).
- Produces: `renderHierarchyTimeline(tree, container)` — the entry point Task 6 wires up from `explore.js`.

Row stack, top to bottom, all sharing the same `createTimeScale` instance and rendered as one flat SVG (matching `app.js`'s established pattern: a single `<svg viewBox="0 0 width height">`, elements appended as flat siblings, positioned with `x`/`width` from the scale rather than nested `<g>` per row):

1. **Geological epoch row** — from `GEOLOGICAL_EPOCHS`, same data as today, now positioned via `scale.x`/`scale.width` instead of `renderGeologicalBand`'s own true-linear-proportional math (so it visually aligns with the rows below it under the same broken axis). Height: one row, `28px`.
2. **Macro chapter row** — `tree.chapters`, one band each, height `36px`, click navigates to `/?era=<id>` (existing, already-shipped deep link from `web/app.js`'s bootstrap era-param handling — unchanged).
3. **Regional era row(s)** — all eras across all chapters, `packIntoLanes` applied per chapter (each chapter's eras packed independently, then chapters' lane-groups concatenated left-to-right since chapters don't overlap in time), `24px` per lane.
4. **Named period row(s)** — same packing approach, one level down, `20px` per lane. Periods with `"curated": false` (Task 1) render with `class="tree-band heuristic"` (dashed border, lower opacity — CSS in Task 6) instead of `class="tree-band curated"`.

- [ ] Write `web/explore_timeline.js`:

```js
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  })[character]);
}

function formatYear(year) {
  if (year === null || year === undefined) return "present";
  return year < 0 ? `${Math.abs(year).toLocaleString()} BCE` : `${year.toLocaleString()} CE`;
}

function svgEl(name, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  return el;
}

function bandRect(svg, { x, y, width, height, cls, title, href }) {
  const group = href ? svgEl("a", { href }) : null;
  const rect = svgEl("rect", { x, y, width, height, class: cls, rx: 2 });
  const titleEl = svgEl("title");
  titleEl.textContent = title;
  rect.append(titleEl);
  if (group) { group.append(rect); svg.append(group); } else { svg.append(rect); }
  return rect;
}

function renderHierarchyTimeline(tree, container) {
  const width = Math.max(900, Math.min(4800, window.innerWidth - 80));
  const scale = createTimeScale(tree.axis.domain_start, tree.axis.domain_end, tree.axis.segment_break, width);

  const geoRowHeight = 28;
  const chapterRowHeight = 36;
  const eraLaneHeight = 24;
  const periodLaneHeight = 20;
  const rowGap = 6;

  // Pack eras and periods per chapter, left-to-right (chapters don't overlap).
  const chapterLayouts = tree.chapters.map((chapter) => {
    const eraLanes = packIntoLanes([...chapter.eras].sort((a, b) => a.start - b.start));
    const allPeriods = chapter.eras.flatMap((era) => era.periods);
    const periodLanes = packIntoLanes([...allPeriods].sort((a, b) => a.start - b.start));
    return { chapter, eraLanes, periodLanes };
  });
  const maxEraLanes = Math.max(1, ...chapterLayouts.map((c) => c.eraLanes.length));
  const maxPeriodLanes = Math.max(1, ...chapterLayouts.map((c) => c.periodLanes.length));

  const eraRowHeight = maxEraLanes * eraLaneHeight;
  const periodRowHeight = maxPeriodLanes * periodLaneHeight;
  const height = geoRowHeight + chapterRowHeight + eraRowHeight + periodRowHeight + rowGap * 4;

  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, class: "hierarchy-chart" });

  let y = 0;
  const geoEnd = new Date().getFullYear();
  for (const epoch of GEOLOGICAL_EPOCHS) {
    const end = epoch.end === null ? geoEnd : epoch.end;
    const bx = scale.x(epoch.start);
    bandRect(svg, {
      x: bx, y, width: scale.width(epoch.start, end), height: geoRowHeight,
      cls: "hierarchy-band hierarchy-band-geo", title: epoch.name,
    });
  }
  y += geoRowHeight + rowGap;

  for (const chapter of tree.chapters) {
    bandRect(svg, {
      x: scale.x(chapter.start), y, width: scale.width(chapter.start, chapter.end), height: chapterRowHeight,
      cls: "hierarchy-band hierarchy-band-chapter",
      title: `${chapter.canonical_name} (${formatYear(chapter.start)} - ${formatYear(chapter.end)})`,
      href: `/?era=${encodeURIComponent(chapter.id)}`,
    });
  }
  y += chapterRowHeight + rowGap;

  chapterLayouts.forEach(({ eraLanes }) => {
    eraLanes.forEach((lane, laneIndex) => {
      lane.forEach((era) => {
        bandRect(svg, {
          x: scale.x(era.start), y: y + laneIndex * eraLaneHeight,
          width: scale.width(era.start, era.end), height: eraLaneHeight - 2,
          cls: "hierarchy-band hierarchy-band-era", title: era.canonical_name,
        });
      });
    });
  });
  y += eraRowHeight + rowGap;

  chapterLayouts.forEach(({ periodLanes }) => {
    periodLanes.forEach((lane, laneIndex) => {
      lane.forEach((period) => {
        const curatedClass = period.curated ? "curated" : "heuristic";
        bandRect(svg, {
          x: scale.x(period.start), y: y + laneIndex * periodLaneHeight,
          width: scale.width(period.start, period.end), height: periodLaneHeight - 2,
          cls: `hierarchy-band hierarchy-band-period ${curatedClass}`, title: period.canonical_name,
        });
      });
    });
  });

  container.replaceChildren(svg);
  return { scale, height };
}
```

- [ ] Manual browser verification: temporarily point `web/explore.js` (not yet wired properly — this is a throwaway check) at `renderHierarchyTimeline` with a hand-fetched `explore_tree.json`, confirm all 9 chapter bands render left-to-right without gaps/overlaps, era bands nest visually within their parent chapter's horizontal span, period bands render (mix of solid/dashed depending on `curated`), and hovering shows the `<title>` tooltip. Revert the throwaway wiring — Task 6 does the real wiring.
- [ ] Commit: `git add web/explore_timeline.js && git commit -m "web: hierarchy timeline renderer (geological/chapter/era/period rows)"`

---

## Task 5: Polities row with region/continent/hide toggle

**Files:**
- Modify: `web/explore_timeline.js`

**Interfaces:**
- Modifies: `renderHierarchyTimeline(tree, container, groupBy = "historical_region")` — `groupBy` is one of `"historical_region"`, `"continent"`, or `"none"` (hide the row entirely). Called by Task 6's toggle-change handler with the same `tree`, re-rendering from scratch (matches `app.js`'s existing "no incremental diffing, full rebuild per render" convention).

Per chapter: one sub-lane group per region key (`polities_by_historical_region` or `polities_by_continent`, chosen by `groupBy`), region groups stacked vertically with a label, `packIntoLanes` applied within each region group (polities can overlap in time within the same region — sibling states, successive dynasties, etc.). To keep a chapter with hundreds of qualifying polities from producing an enormous row, cap each region group to the first 15 entries (already sorted by `start` per Task 1) plus a "+N more" label — a rendering-time cap, not a data-time one (Task 1 Step 3 deliberately ships every entry; the count therefore stays honest even though the render trims it).

- [ ] Extend `web/explore_timeline.js`:

```js
const POLITY_LANE_HEIGHT = 18;
const REGION_HEADER_HEIGHT = 16;
const MAX_POLITIES_PER_REGION = 15;

function regionLabel(key) {
  if (key === "unclassified") return "Unclassified";
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function renderPolitiesRow(svg, scale, chapter, groupBy, y) {
  if (groupBy === "none") return y;
  const buckets = groupBy === "continent" ? chapter.polities_by_continent : chapter.polities_by_historical_region;
  const regionKeys = Object.keys(buckets).sort();
  let rowY = y;
  for (const key of regionKeys) {
    const entries = buckets[key];
    const shown = entries.slice(0, MAX_POLITIES_PER_REGION);
    const lanes = packIntoLanes(shown);
    const label = svgEl("text", { x: scale.x(chapter.start), y: rowY + REGION_HEADER_HEIGHT - 4, class: "hierarchy-region-label" });
    label.textContent = `${regionLabel(key)} (${entries.length})`;
    svg.append(label);
    rowY += REGION_HEADER_HEIGHT;
    lanes.forEach((lane, laneIndex) => {
      lane.forEach((polity) => {
        const curatedClass = polity.curated ? "curated" : "heuristic";
        bandRect(svg, {
          x: scale.x(polity.start), y: rowY + laneIndex * POLITY_LANE_HEIGHT,
          width: scale.width(polity.start, polity.end), height: POLITY_LANE_HEIGHT - 2,
          cls: `hierarchy-band hierarchy-band-polity ${curatedClass}`, title: polity.canonical_name,
        });
      });
    });
    rowY += lanes.length * POLITY_LANE_HEIGHT + 4;
  }
  return rowY;
}
```

- [ ] Modify `renderHierarchyTimeline`'s signature to `function renderHierarchyTimeline(tree, container, groupBy = "historical_region")`. Add a `measurePolitiesRowHeight(chapter, groupBy)` helper that mirrors `renderPolitiesRow`'s traversal but only sums heights (no SVG writes), so the row height is known before the `<svg>` is created — the same measure-then-draw two-pass shape the era/period rows already use via `chapterLayouts`/`maxEraLanes`/`maxPeriodLanes`:

```js
function measurePolitiesRowHeight(chapter, groupBy) {
  if (groupBy === "none") return 0;
  const buckets = groupBy === "continent" ? chapter.polities_by_continent : chapter.polities_by_historical_region;
  let total = 0;
  for (const entries of Object.values(buckets)) {
    const shown = entries.slice(0, MAX_POLITIES_PER_REGION);
    const lanes = packIntoLanes(shown);
    total += REGION_HEADER_HEIGHT + lanes.length * POLITY_LANE_HEIGHT + 4;
  }
  return total;
}
```

  Then in `renderHierarchyTimeline`: after computing `periodRowHeight` and before `const height = ...`, add `const politiesRowHeight = Math.max(0, ...tree.chapters.map((c) => measurePolitiesRowHeight(c, groupBy)));` and fold it into the total: `const height = geoRowHeight + chapterRowHeight + eraRowHeight + periodRowHeight + politiesRowHeight + rowGap * 5;` (five gaps now, one per row boundary including the new row). After the existing period-row drawing loop and its `y += periodRowHeight + rowGap;`, add: `for (const chapter of tree.chapters) { renderPolitiesRow(svg, scale, chapter, groupBy, y); }` — every chapter's polities row starts at the same shared `y` (chapters sit side by side horizontally, same as the era/period rows), so no further `y` bookkeeping is needed after this loop.
- [ ] Manual browser verification, same scratch-throwaway method as Task 4: confirm switching `groupBy` between `"historical_region"`, `"continent"`, and `"none"` changes the polities row correctly (including removing it and shrinking the chart height for `"none"`), region labels show correct counts, and a region with >15 entries only draws 15 bands but still labels the true count.
- [ ] Commit: `git add web/explore_timeline.js && git commit -m "web: add polities row with historical-region/continent/hide toggle"`

---

## Task 6: Wire `/explore` to the new renderer

**Files:**
- Modify: `web/explore.html`
- Modify: `web/explore.js`
- Modify: `web/styles.css`

**Interfaces:**
- Consumes: `renderHierarchyTimeline` (Tasks 4-5), `/explore_tree.json` (Task 1).

- [ ] In `web/explore.html`: replace `<p>Nine chapters, oldest first. Click one to zoom in.</p>` with `<p>Nine chapters, oldest first. Click a chapter to open it on the full timeline.</p>` (the click-through behavior is unchanged, just no longer tile-shaped); remove `<div id="geological-band" aria-hidden="true"></div>` and `<main id="chapter-grid" class="chapter-grid" aria-label="Macro chapters">` — replace with:

```html
    <div class="hierarchy-controls" aria-label="Polities display">
      <label for="polities-toggle">Show polities by</label>
      <select id="polities-toggle">
        <option value="historical_region">Historical region</option>
        <option value="continent">Present-day continent</option>
        <option value="none">Hidden</option>
      </select>
    </div>
    <div id="hierarchy-chart" class="hierarchy-chart-container" aria-label="Period hierarchy timeline">
      <p class="loading">Loading…</p>
    </div>
```

  and update the script tags to also load the three new files, in dependency order:

```html
    <script src="/static/geological_epochs.js"></script>
    <script src="/static/timeline_scale.js"></script>
    <script src="/static/lane_packing.js"></script>
    <script src="/static/explore_timeline.js"></script>
    <script src="/static/explore.js"></script>
```

- [ ] Rewrite `web/explore.js` end to end:

```js
async function main() {
  const container = document.querySelector("#hierarchy-chart");
  const toggle = document.querySelector("#polities-toggle");
  try {
    const response = await fetch("/explore_tree.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const tree = await response.json();
    const draw = () => renderHierarchyTimeline(tree, container, toggle.value);
    draw();
    toggle.addEventListener("change", draw);
  } catch (error) {
    container.innerHTML = `<p class="error">Could not load explore_tree.json (${error.message}). Run the build command from the repository root.</p>`;
  }
}

main();
```

  (`escapeHtml`, `formatYear`, and `renderGeologicalBand` move into/are superseded by `explore_timeline.js` — Task 4 already inlined `escapeHtml`/`formatYear` there and folded the geological band into the row stack, so this file no longer needs its own copies.)

- [ ] In `server/app.py`, verify the `web_dir` static-file mount already serves any file under `web/` at `/static/<name>` (it does for every existing `web/*.js` — check the existing `StaticFiles` mount if any doubt) so `timeline_scale.js`/`lane_packing.js`/`explore_timeline.js` need no new route.
- [ ] Add to `web/styles.css` (near the existing `.chapter-grid`/`.chapter-tile` rules — replace those two rules entirely, they're dead code once the tile grid is gone; check for other consumers with `grep -n "chapter-grid\|chapter-tile" web/*.html` first):

```css
.hierarchy-controls { display: flex; gap: .6rem; align-items: center; padding: .6rem clamp(1rem, 4vw, 3.5rem); font: .82rem system-ui, sans-serif; color: var(--ink-faint); }
.hierarchy-chart-container { overflow: auto; padding: 0 clamp(1rem, 4vw, 3.5rem) 2rem; }
.hierarchy-chart { display: block; min-width: 740px; }
.hierarchy-band { fill: var(--paper); stroke: var(--rule); cursor: pointer; }
.hierarchy-band-geo { fill: #eee9de; stroke: none; cursor: default; }
.hierarchy-band-chapter { fill: #8c422d; fill-opacity: .18; stroke: #8c422d; }
.hierarchy-band-era { fill: #27251f; fill-opacity: .1; }
.hierarchy-band-period.curated { fill: #27251f; fill-opacity: .16; }
.hierarchy-band-period.heuristic, .hierarchy-band-polity.heuristic { fill-opacity: .07; stroke-dasharray: 3 2; }
.hierarchy-band-polity.curated { fill: #34506b; fill-opacity: .22; }
.hierarchy-region-label { font: .72rem system-ui, sans-serif; fill: var(--ink-faint); }
```

- [ ] Manual full-page QA in a browser (`make serve` or the project's documented Windows equivalent — rebuild first so `explore_tree.json` exists): load `/explore`, confirm the geological/chapter/era/period rows render aligned on the same axis, the polities toggle switches correctly between historical region / continent / hidden, clicking a chapter band navigates to `/?era=<id>` and (per the already-shipped fix) both zooms the date range and selects the matching "Historical period" dropdown entry, and the nav bar's "Explore" link still highlights `aria-current="page"` correctly.
- [ ] Run the full Python suite once more (`python -m unittest discover -s tests -v`) to confirm the Task 1 pipeline changes are still green after everything else landed on top.
- [ ] Commit: `git add web/explore.html web/explore.js web/styles.css && git commit -m "web: wire /explore to the hierarchy timeline renderer, retire the tile grid"`

---

## Task 7: Docs

**Files:**
- Modify: `ONTOLOGY.md`
- Modify: `PLAN.md`
- Modify: `README.md` (only if the build/serve instructions need a new step — they shouldn't, since `explore_tree.json` is written by the same `build.py` run as everything else; verify, don't assume)

- [ ] In `ONTOLOGY.md`'s "How a future timeline UI should read this" section, change the framing from forward-looking ("How a future timeline UI should read this... deeper zoom levels are scoped as a roadmap there, not yet task-level") to descriptive of what's shipped: note that `/explore` (as of `docs/plans/2026-08-30-explore-hierarchy-timeline.md`) now renders the full chapter → era → period hierarchy plus a region-toggleable polities row, built by `pipeline/build_explore_tree.py` into `explore_tree.json`, and that curated vs. heuristic placement (Task 1's `"curated"` flag) is the honest way this view stays populated ahead of the `period_links.yaml`/`broader_periods` curation queues being fully worked.
- [ ] In `PLAN.md`, add a phase row for this plan (matching the existing phase-row convention for the two prior 2026-08-29 plans) and remove/update the "Explore chapter tiles" description if `PLAN.md` currently describes the tile-grid behavior anywhere (`grep -n -i explore PLAN.md` first).
- [ ] Commit: `git add ONTOLOGY.md PLAN.md README.md && git commit -m "docs: describe the shipped Explore hierarchy timeline"`

---

## Notes for the implementer / reviewer

- **Non-obvious call, flagged for the user to weigh in on during plan review:** heuristic placement (Task 1 Step 3, rules 3-4) computes a best-effort chapter/era for polities and periods that have no curated link yet, rather than leaving those rows empty until the suggestion queues are fully worked. This trades some placement accuracy (a heuristic placement can be wrong, same caveat already documented for `suggest_period_links.py`/`suggest_regional_eras.py`'s own output) for a page that's actually useful today. Heuristic entries are visually distinguished (dashed/lower-opacity, Task 6's CSS) specifically so this tradeoff stays honest to the viewer rather than silently blurring curated fact with best-guess placement.
- **Deliberately out of scope:** refactoring `app.js`'s existing lane-packing/relationship-ordering code to share code with `web/lane_packing.js`. `app.js`'s `orderLaneEntities` does more (relationship-aware clustering, not just interval packing) and has no test coverage to protect a refactor; `web/lane_packing.js` is a smaller, purpose-built primitive for this view. Revisit only if a third consumer needs the exact same relationship-clustering behavior.
- **Deliberately out of scope:** the `Period.tier`/`broader_periods` curation queues (`reports/regional_era_suggestions.jsonl`, `reports/period_link_suggestions.jsonl`) themselves. This plan makes the Explore page useful despite sparse curation, not the other way around — working those queues down is separate, already-tracked follow-up work.
