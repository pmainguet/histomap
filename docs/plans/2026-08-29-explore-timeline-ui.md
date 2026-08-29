# Explore Timeline UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new, curated "Explore" entry point (`/explore`) that opens on the 9 macro chapters — the simplest possible view — with a geological reference band shown alongside it, and a scoped, not-yet-detailed roadmap for the deeper zoom levels (regional era → period → entity) once this first slice is proven out. This is the "start from a new timeline page, simpler to more complex" work from the start of this conversation, now unblocked by the period-ontology plan.

**Architecture:** Extends the existing FastAPI + vanilla-JS app (`server/app.py`, `web/*.html`/`*.js`, no framework, no build step) rather than introducing a new stack. A new `pipeline/build_explore_index.py` step, wired into `build.py`, turns `pipeline/period_hierarchy.py`'s `PeriodHierarchy` into a small precomputed `explore_index.json` (same pattern as `periods.json`/`period_links.json` — a build artifact the server just serves as a static file, no per-request computation). A new static page (`web/explore.html` + `web/explore.js`) renders it, following the existing page's exact visual language (Georgia serif, parchment palette, same header/nav).

**Tech Stack:** Python 3.12 (FastAPI, Pydantic), vanilla JS/HTML/CSS (no framework — matches `web/app.js`), `unittest`.

**Spec:** [`ONTOLOGY.md`](../../ONTOLOGY.md) for the data model this renders, and [`docs/plans/2026-08-29-period-ontology.md`](2026-08-29-period-ontology.md) for the data layer this depends on.

**Depends on:** the period-ontology plan's Task 3 (9 macro chapters must exist), Task 7 (`pipeline/period_hierarchy.py` must exist), and ideally Task 6 (polity → period links — without it, `top_entities()` on most chapters returns few or no results; the "World" view still renders correctly, just sparsely, which is itself useful signal for how much of Task 6's queue is worth working through).

## Global Constraints

- Follow the existing page's house style exactly: Georgia/Times serif, the parchment palette already defined in `web/styles.css`'s `:root` (`--paper: #f9f5ea`, `--rule: #c7beaa`, ink `#27251f`, accent `#8c422d`), the same header/nav markup pattern as `web/index.html`. Do not introduce a CSS framework, build step, or new font.
- No new Python dependencies. FastAPI/Pydantic/PyYAML only, matching everything else in this repo.
- `python -m unittest discover -s tests` and `python build.py` must stay green after every task.
- This plan's Task 1-3 build a real, working "World" zoom level. Everything past that (regional-era zoom, entity detail, parallel lanes) is a **roadmap**, not checkbox tasks — writing detailed code for a zoom level nobody's used yet risks building the wrong thing. Extend this plan with real tasks for the next phase once Phase 1 has been used and something concrete is learned from it.

---

## File structure

- Create: `pipeline/build_explore_index.py` + `tests/test_build_explore_index.py` (Task 1)
- Modify: `build.py` — call the new builder, write `explore_index.json`
- Modify: `.gitignore` — `explore_index.json` (generated, like `data.json`; not source of truth)
- Create: `web/explore.html`, `web/explore.js` (Task 2)
- Modify: `server/app.py` — new `/explore` page route, new `/explore_index.json` data route
- Modify: `web/styles.css` — a handful of new rules for the chapter-tile grid and the geological band, appended, not restructuring existing rules
- Create: `web/geological_epochs.js` (Task 3) — static reference data, no backend

---

## Task 1: `explore_index.json` build step

**Files:**
- Create: `pipeline/build_explore_index.py`
- Create: `tests/test_build_explore_index.py`
- Modify: `build.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `pipeline.period_hierarchy.PeriodHierarchy` (from the period-ontology plan's Task 7)
- Produces: `build_explore_index(polities: list[dict], periods: list[dict], period_links: list[dict], top_n: int = 8) -> list[dict]`, called from `build.py`'s `main()` with the same `published_polities`/`periods`/`period_links` data it already computes (no duplicate file reads) and written to `explore_index.json`

Each entry: `{id, canonical_name, start, end, entity_count, top_entities: [{id, canonical_name, start, end}]}` — everything `web/explore.js` needs to render a chapter tile without a second round-trip.

- [ ] **Step 1: Write the failing test**

Create `tests/test_build_explore_index.py`:

```python
import unittest

from pipeline.build_explore_index import build_explore_index


def polity(id_: str, score: float, start: int = 0, end: int | None = 100) -> dict:
    return {
        "id": id_,
        "canonical_name": id_.replace("_", " ").title(),
        "start": start,
        "end": end,
        "prominence_score": score,
    }


class BuildExploreIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.periods = [
            {"id": "macro_a", "tier": "macro_chapter", "canonical_name": "Chapter A", "start": 0, "end": 1000, "broader_periods": []},
            {"id": "macro_b", "tier": "macro_chapter", "canonical_name": "Chapter B", "start": 1000, "end": 2000, "broader_periods": []},
            {"id": "period_a", "tier": "period", "canonical_name": "Period A", "start": 100, "end": 200, "broader_periods": ["macro_a"]},
        ]
        self.period_links = [
            {"period_id": "period_a", "entity_id": "polity_1"},
            {"period_id": "period_a", "entity_id": "polity_2"},
        ]
        self.polities = [polity("polity_1", 90), polity("polity_2", 10)]

    def test_one_entry_per_macro_chapter_ordered_by_start(self) -> None:
        result = build_explore_index(self.polities, self.periods, self.period_links)
        self.assertEqual([r["id"] for r in result], ["macro_a", "macro_b"])

    def test_entity_count_and_ranked_top_entities(self) -> None:
        result = build_explore_index(self.polities, self.periods, self.period_links, top_n=1)
        chapter_a = next(r for r in result if r["id"] == "macro_a")
        self.assertEqual(chapter_a["entity_count"], 2)
        self.assertEqual(len(chapter_a["top_entities"]), 1)
        self.assertEqual(chapter_a["top_entities"][0]["id"], "polity_1")  # higher prominence_score

    def test_chapter_with_no_linked_entities_still_included(self) -> None:
        result = build_explore_index(self.polities, self.periods, self.period_links)
        chapter_b = next(r for r in result if r["id"] == "macro_b")
        self.assertEqual(chapter_b["entity_count"], 0)
        self.assertEqual(chapter_b["top_entities"], [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_build_explore_index -v`
Expected: `ImportError`.

- [ ] **Step 3: Write the builder**

Create `pipeline/build_explore_index.py`:

```python
"""Build-time step: precompute explore_index.json (the World zoom level's
data) from the period hierarchy. Server-served as a static file, same
pattern as periods.json/period_links.json -- no per-request computation."""

from __future__ import annotations

from pipeline.period_hierarchy import PeriodHierarchy


def build_explore_index(
    polities: list[dict], periods: list[dict], period_links: list[dict], top_n: int = 8
) -> list[dict]:
    hierarchy = PeriodHierarchy(periods=periods, period_links=period_links, polities=polities)
    polities_by_id = {p["id"]: p for p in polities}
    entries = []
    for chapter_id in hierarchy.macro_chapters():
        chapter = next(p for p in periods if p["id"] == chapter_id)
        entity_ids = hierarchy.entities_under(chapter_id)
        top_ids = hierarchy.top_entities(chapter_id, limit=top_n)
        entries.append(
            {
                "id": chapter_id,
                "canonical_name": chapter["canonical_name"],
                "start": chapter["start"],
                "end": chapter["end"],
                "entity_count": len(entity_ids),
                "top_entities": [
                    {
                        "id": eid,
                        "canonical_name": polities_by_id[eid]["canonical_name"],
                        "start": polities_by_id[eid]["start"],
                        "end": polities_by_id[eid].get("end"),
                    }
                    for eid in top_ids
                ],
            }
        )
    return entries
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m unittest tests.test_build_explore_index -v`
Expected: PASS.

- [ ] **Step 5: Wire into `build.py`**

Add near the top of `build.py`, alongside the other `*_OUT_PATH` constants:

```python
EXPLORE_INDEX_OUT_PATH = ROOT / "explore_index.json"
```

In `main()`, after the existing `PERIOD_LINKS_OUT_PATH.write_text(...)` block, add:

```python
    from pipeline.build_explore_index import build_explore_index

    explore_index = build_explore_index(
        [p.model_dump(mode="json") for p in published_polities],
        [p.model_dump(mode="json") for p in periods],
        [link.model_dump(mode="json") for link in period_links],
    )
    EXPLORE_INDEX_OUT_PATH.write_text(
        json.dumps(explore_index, indent=2, ensure_ascii=False), encoding="utf-8"
    )
```

(The `from ... import` is inline rather than top-of-file to avoid a circular import if `pipeline/build_explore_index.py` or `pipeline/period_hierarchy.py` ever need something from `build.py` later — check on implementation whether that's actually a risk before deciding to keep it inline or hoist it; it's not currently.)

Add to `.gitignore`, next to `data.json`:

```
explore_index.json
```

- [ ] **Step 6: Run build and full suite**

Run: `.venv/Scripts/python.exe build.py`
Expected: `OK` with the usual counts, plus `explore_index.json` now exists at repo root.

Run: `.venv/Scripts/python.exe -c "import json; data = json.load(open('explore_index.json', encoding='utf-8')); print(len(data), 'chapters'); [print(c['id'], c['entity_count']) for c in data]"`
Expected: 9 lines, one per macro chapter.

Run: `.venv/Scripts/python.exe -m unittest discover -s tests -v` — all green.

- [ ] **Step 7: Commit**

```bash
git add pipeline/build_explore_index.py tests/test_build_explore_index.py build.py .gitignore
git commit -m "build: add explore_index.json (World zoom level data)"
```

---

## Task 2: The "World" page

**Files:**
- Create: `web/explore.html`
- Create: `web/explore.js`
- Modify: `server/app.py` — new routes
- Modify: `web/styles.css` — append tile-grid rules
- Modify: `web/index.html`, and every other `web/*.html` with the shared nav — add an "Explore" link

**Interfaces:**
- Consumes: `explore_index.json` (Task 1)
- Produces: `/explore`, a page showing the 9 macro chapters as tiles (name, date range, entity count, top 3 entity names), each linking through to `/?era=<id>` on the existing `/` timeline for now (Phase 2 gives it a real destination — see Roadmap)

- [ ] **Step 1: Add the FastAPI routes**

In `server/app.py`, alongside the existing page/data routes:

```python
    @application.get("/explore", include_in_schema=False)
    async def explore_page() -> FileResponse:
        return FileResponse(web_dir / "explore.html")

    @application.get("/explore_index.json", include_in_schema=False)
    async def explore_index() -> FileResponse:
        path = root / "explore_index.json"
        if not path.exists():
            raise HTTPException(404, "Run the build action first")
        return FileResponse(path)
```

- [ ] **Step 2: Write the page**

Create `web/explore.html`, copying `web/index.html`'s `<head>` and `.site-header` block verbatim (same brand mark, same nav — add `<a href="/explore" aria-current="page">Explore</a>` here and a plain `<a href="/explore">Explore</a>` into every other page's nav, matching how `/reviews` is already cross-linked), then:

```html
    <section class="explore-intro" aria-label="About this view">
      <h1>Explore human history</h1>
      <p>Nine chapters, largest first. Click one to zoom in.</p>
    </section>
    <div id="geological-band" aria-hidden="true"></div>
    <main id="chapter-grid" class="chapter-grid" aria-label="Macro chapters">
      <p class="loading">Loading…</p>
    </main>
    <script src="/static/geological_epochs.js"></script>
    <script src="/static/explore.js"></script>
  </body>
</html>
```

- [ ] **Step 3: Write the renderer**

Create `web/explore.js`:

```javascript
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  })[character]);
}

function formatYear(year) {
  if (year === null || year === undefined) return "present";
  return year < 0 ? `${Math.abs(year).toLocaleString()} BCE` : `${year.toLocaleString()} CE`;
}

function renderChapter(chapter) {
  const topNames = chapter.top_entities.map((e) => escapeHtml(e.canonical_name)).join(", ") || "no linked entities yet";
  return `
    <a class="chapter-tile" href="/?era=${encodeURIComponent(chapter.id)}">
      <h2>${escapeHtml(chapter.canonical_name)}</h2>
      <p class="chapter-span">${formatYear(chapter.start)} – ${formatYear(chapter.end)}</p>
      <p class="chapter-count">${chapter.entity_count.toLocaleString()} entities</p>
      <p class="chapter-top">${topNames}</p>
    </a>`;
}

async function main() {
  const grid = document.querySelector("#chapter-grid");
  try {
    const response = await fetch("/explore_index.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const chapters = await response.json();
    grid.innerHTML = chapters.map(renderChapter).join("");
  } catch (error) {
    grid.innerHTML = `<p class="error">Could not load explore_index.json (${error.message}). Run the build command from the repository root.</p>`;
  }
}

main();
```

- [ ] **Step 4: Append CSS**

Add to the end of `web/styles.css` (do not restructure existing rules):

```css
.explore-intro { padding: 1.5rem clamp(1rem, 4vw, 3.5rem) 0; }
.explore-intro h1 { margin: 0 0 .3rem; font-size: 2rem; }
.explore-intro p { margin: 0; color: var(--ink-faint); }
.chapter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
  gap: 1rem;
  padding: 1.5rem clamp(1rem, 4vw, 3.5rem) 3rem;
}
.chapter-tile {
  display: block;
  padding: 1.1rem;
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: 3px;
  color: inherit;
  text-decoration: none;
}
.chapter-tile:hover { border-color: #8c422d; }
.chapter-tile h2 { margin: 0 0 .3rem; font-size: 1.15rem; }
.chapter-span { margin: 0 0 .2rem; color: var(--ink-faint); font: .82rem system-ui, sans-serif; }
.chapter-count { margin: 0 0 .5rem; font: 700 .8rem system-ui, sans-serif; color: #8c422d; }
.chapter-top { margin: 0; font-size: .88rem; }
```

- [ ] **Step 5: Manual check**

Run: `.venv/Scripts/python.exe -m server.app` (or however `make serve` invokes it — check the Makefile's `serve` target for the exact command) and open `http://127.0.0.1:8000/explore`. Expected: 9 tiles, contemporary-world-first-or-last depending on your reading of "largest first" (this plan renders in chronological order — reconsider "largest first" copy in `explore.html` if entity counts turn out heavily skewed toward one end, which is likely given the dataset's modern-history bias; adjust the intro copy once you see real numbers, don't guess now).

- [ ] **Step 6: Commit**

```bash
git add web/explore.html web/explore.js web/styles.css server/app.py web/index.html web/review.html web/reviews.html web/consolidation_review.html web/type_review.html web/subdivision_review.html web/period_review.html
git commit -m "web: add /explore World zoom level (9 macro chapter tiles)"
```

---

## Task 3: Geological reference band (Holocene, displayed alongside)

**Files:**
- Create: `web/geological_epochs.js`
- Modify: `web/explore.js`, `web/styles.css`

**Interfaces:**
- Produces: a thin, static reference band rendered under the chapter grid, showing Pleistocene/Holocene (Greenlandian/Northgrippian/Meghalayan) boundaries — informational only, no click targets, no backend, no `Period` records (per `ONTOLOGY.md`: "a static UI asset... zero coupling to `broader_periods`/`tier`/`period_links.yaml`")

- [ ] **Step 1: Write the static reference data**

Create `web/geological_epochs.js`:

```javascript
// ICS-ratified boundaries (2018), converted to the calendar-year display
// convention used elsewhere in this app. Deliberately NOT a periods/*.yaml
// record or a Period.tier value -- see ONTOLOGY.md's "Why this exists" and
// "Tree, lanes, graph" sections for why this stays a static display-only
// asset rather than a data-layer citizen.
const GEOLOGICAL_EPOCHS = [
  { id: "pleistocene", name: "Pleistocene", start: -2588000, end: -9701 },
  { id: "greenlandian", name: "Greenlandian (Early Holocene)", start: -9701, end: -6237 },
  { id: "northgrippian", name: "Northgrippian (Middle Holocene)", start: -6237, end: -2251 },
  { id: "meghalayan", name: "Meghalayan (Late Holocene)", start: -2251, end: null },
];
```

- [ ] **Step 2: Render it**

Add to `web/explore.js`, called from `main()` right after `grid.innerHTML = ...`:

```javascript
function renderGeologicalBand() {
  const band = document.querySelector("#geological-band");
  const overallStart = GEOLOGICAL_EPOCHS[0].start;
  const overallEnd = new Date().getFullYear();
  const span = overallEnd - overallStart;
  band.innerHTML = GEOLOGICAL_EPOCHS.map((epoch) => {
    const end = epoch.end === null ? overallEnd : epoch.end;
    const widthPct = ((end - epoch.start) / span) * 100;
    return `<div class="geo-segment" style="width:${widthPct}%" title="${escapeHtml(epoch.name)}">${escapeHtml(epoch.name)}</div>`;
  }).join("");
}
```

Call `renderGeologicalBand();` at the top of `main()`, before the `fetch("/explore_index.json")` call — it doesn't depend on server data, so it should render immediately rather than waiting.

- [ ] **Step 3: Append CSS**

Add to `web/styles.css`:

```css
#geological-band {
  display: flex;
  margin: 0 clamp(1rem, 4vw, 3.5rem);
  border: 1px solid var(--rule);
  border-radius: 2px;
  overflow: hidden;
  font: .72rem system-ui, sans-serif;
}
.geo-segment {
  padding: .3rem .4rem;
  border-right: 1px solid var(--rule);
  background: #e4ded0;
  color: var(--ink-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.geo-segment:last-child { border-right: none; }
```

Given `overallStart` is -2,588,000 (Pleistocene start) and the macro chapters span to -3,000,000, the geological band deliberately doesn't cover the full chapter-grid width — it's a reference for "how deep is deep," not a proportional timeline axis lined up under the tiles. Don't try to pixel-align it with `.chapter-grid` below; that's a Phase 2+ concern once there's an actual proportional timeline axis to align against (see Roadmap).

- [ ] **Step 4: Manual check, commit**

Reload `/explore`. Expected: a thin four-segment bar above the chapter grid, each segment showing a geological epoch name, roughly proportioned (Meghalayan — the last ~4,250 years — will render as a sliver next to Pleistocene's much longer span; that's correct, not a bug).

```bash
git add web/geological_epochs.js web/explore.js web/styles.css
git commit -m "web: add static geological epoch reference band to /explore"
```

---

## Roadmap (not yet planned in task-level detail)

Writing full checkbox tasks for these now would mean guessing at UI decisions nobody's validated yet against a real "World" view. Concrete enough to scope, not concrete enough to code blind:

- **Phase 2 — zoom into a chapter.** `/explore?chapter=<id>` (or a dedicated route) showing that chapter's `children()` (regional eras) as a second grid, `top_entities()` for each, and an `ancestors()`-driven breadcrumb. Mostly reuses Task 1/2's pattern once `explore_index.json`'s shape is extended to carry a chapter's children, not just its top entities.
- **Phase 3 — entity detail.** Clicking through to a specific polity should land in `web/index.html`'s existing detail drawer (`app.js` already has this fully built for the current flat view) rather than building a second detail UI — the `/explore` page ends at "show me the polity," the existing page already does "here's everything about it."
- **Phase 4 — parallel lanes.** Per `ONTOLOGY.md`'s "Tree, lanes, graph" section — computed client-side from `geography`/`entity_type` on whatever set of entities the current zoom level is showing, not persisted. Needs an actual zoomed-in view with real entities in it (Phase 2) before lane layout is worth designing.
- **Phase 5 — historical region as a filter facet**, once the period-ontology plan's Task 9 (`historical_regions`) has real coverage data to filter on.

## Self-review

**Spec coverage** — the two items explicitly asked to be "included in the plan" (the timeline UI itself, and the Holocene display layer) both have real, committable tasks (2 and 3). The historical-region ask went into the period-ontology plan instead (Task 9 there) since it's data-layer work, not UI — noted here so it's not silently missing from this document.

**Placeholder scan** — Task 5's manual-check step flags a real open question ("largest first" copy vs. actual chronological rendering) rather than guessing at it; the Roadmap section is explicitly labeled as not-yet-task-level rather than padded out with fake checkboxes.

**Type consistency** — `explore_index.json`'s shape (`id`, `canonical_name`, `start`, `end`, `entity_count`, `top_entities`) is defined once in Task 1 and consumed with the same field names in Task 2's `explore.js`.

## Explicitly out of scope

- Phases 2-5 above (roadmap only).
- Any change to the existing `/` timeline page or `app.js` beyond adding a nav link to `/explore`.
- Authentication/write access — `/explore` is read-only, same trust model as the existing `/` page.
