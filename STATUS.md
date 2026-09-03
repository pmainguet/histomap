# Histomap — Status

Retrospective: what's implemented, current dataset metrics, and the phase-by-phase build
narrative. For project context and how to run things, see [README.md](README.md); for what's
next, see [ROADMAP.md](ROADMAP.md); for the classification system the dataset is organized
around, see [ONTOLOGY.md](ONTOLOGY.md).

---

## Implementation status — 29 August 2026

This section is the current source of truth. Detailed phase descriptions below retain design context,
including targets that are not yet complete.

| Phase | Status | Implemented | Still required |
|---|---|---|---|
| 0 — Foundations | **Mostly complete** | Pydantic schema, canonical YAML, Makefile, build and test suite | Install a pre-commit validation hook; optional Windows-native task wrapper |
| 1 — Wikidata backbone | **Partial** | Extraction, caching, direct-type rules (expanded 31 August 2026 -- see below), YAML import, prominence tiers, relationships, geography, entity-consolidation dashboard, subdivision-parent classification | Resolve 655 remaining type-eligibility review flags and 2,677 pending entity-type classifications; work down the consolidation queue (1,525 of 4,697 still pending, confirmed live 1 September 2026; an automated `suggested_decision` hint covers most of the active queue, now spanning same_entity/detail_of/candidate_detail_of/independent -- phase_of and part_of merged into detail_of the same day, see below); accept reviewed display groups; improve relationship review |
| 2 — Seshat overlay | **Nearly done** | Equinox extraction, fuzzy/date/geography reconciliation, review report, 10/10 spot checks, reviewable "review" sub-queue fully cleared (258 decisions applied, confirmed live 31 August 2026) | 34 unmatched records still need an import-workflow decision (not currently an actionable queue); auto-match rate holds at 81/373 (21.7%), still short of the 60% target |
| 3 — Weights | **Initial implementation** | Maddison/HYDE extraction, mapping, tunable coefficients, sparse era weights | Historical polygon allocation and measured area/complexity; the large majority of records are still imputed |
| 4 — Review workflow | **Partial, in active use** | Three ongoing curation UIs (consolidation, entity-type, subdivision-parent) with provenance, score explanations, source links, saved decisions, pipeline actions; `/review` (Seshat reconciliation matching) retired 31 August 2026 once its queue emptied out -- `pipeline/reconcile.py`/`apply_review_decisions.py` stay as scripts/API hooks | Complete review pass across the three remaining queues; cost estimator and optional structured LLM proposal/diff workflow |
| 5 — Editorial pass | **Started** | Validated transition model and 5 curated transitions | Roughly 45 more transitions, icons for top ~50, and polished adult/child copy for top ~50 |
| 6 — Web view | **Mostly complete** | Unified FastAPI server; `/explore`'s hierarchy timeline (chapter/era/period/polity/civilizations-culture bands) is now the sole web view — `/` (the original flat geographic-lane timeline) was retired 31 August 2026, see below; geographic lane grouping, click-to-zoom, side-panel detail drawer with editing, sources, transitions view | `/`'s free-text search, visibility-tier/entity-type/period-kind filters, era presets/manual date-range input, relationship highlighting on the chart, swimlane collapse/expand, and keyboard-operable bands were deliberately not ported (accepted losses, see ROADMAP.md history) — no longer "still required" so much as "decided against"; reviewed collapsible display groups, linked map, stronger mobile/visual testing, authentication before public write access |
| 7 — Print poster | **Not started** | — | A1/A0 SVG renderer, methodology/legend footer, PDF export and print test |
| 8 — Grow with the kid | **Ongoing later work** | Adult/Child selector, extensible text model, period pilot (90 period records as of 31 August 2026 — down from 102 as period→polity conversions removed several) with role review | Substantial content, more reading levels, language UI, family-history layer |
| 9 — Period ontology | **Foundational layer done** | `Period.tier` schema field, build-time tier/cycle validation, 9 macro chapters, 20 hand-curated + auto-generated modern regional eras, suggestion queues for regional-era and polity period-links, tested `pipeline/period_hierarchy.py` query layer (`top_entities` replaces the retired competitive visibility-tier algorithm), `Geography.historical_regions`/`primary_historical_region` derived from `present_countries` via a starter lookup table | Work the two suggestion queues (`reports/regional_era_suggestions.jsonl`, `reports/period_link_suggestions.jsonl`); grow `pipeline/historical_regions.py`'s ~110-country starter table; replace auto-generated modern regional eras with hand-curated sub-continental ones over time; the timeline UI itself (separate plan) reads `pipeline/period_hierarchy.py` |

### Implementation plans (detailed specifications)

The phases above are implemented via focused implementation plans, each with its own spec and task breakdown:

| Plan | Status | Focus |
|---|---|---|
| [`docs/plans/2026-08-29-period-ontology.md`](docs/plans/2026-08-29-period-ontology.md) | **Complete** | Phase 9 — Chronological hierarchy (macro chapter → regional era → period), build-time tier validation, scoped ranking via `top_entities()`, removal of retired competitive visibility-tier algorithm |
| [`docs/plans/2026-08-29-explore-timeline-ui.md`](docs/plans/2026-08-29-explore-timeline-ui.md) | **Replaced by 2026-08-30** | Initial outline for `/explore` timeline UI (replaced by the plan below once the data layer was ready) |
| [`docs/plans/2026-08-30-explore-hierarchy-timeline.md`](docs/plans/2026-08-30-explore-hierarchy-timeline.md) | **Complete** | Phase 9 → 6 — Full period hierarchy rendering on `/explore`: macro chapter, regional era, named period, and region-toggleable polities band; heuristic placement for sparse curation |

### `/explore` hierarchy timeline — status, 30 August 2026

The plan above shipped the initial version; everything below is post-launch iteration driven
by live testing on the running page, executed as a sequence of small branches (no separate
plan doc per change — each was reviewed and merged individually; see `git log` for the full
commit trail).

**Implemented:**
- Click-to-zoom on any band (chapter/era/period/polity), narrowing the visible date range in
  place; a "Full timeline" control resets. Replaced the original chapter-click behavior of
  navigating to `/` — the `/?era=X` deep link itself still works for anyone who lands on it
  directly.
- The curated/heuristic distinction (dashed vs. solid bands) is live and functional — an
  earlier bug that made every entry heuristic regardless of real `period_links.yaml` curation
  was found and fixed during the initial plan's final review.
- On-band visible labels (not just hover tooltips) for every tier, with label-aware lane
  packing so two adjacent items whose *labels* (not just their date bands) would visually
  overlap get pushed to separate lanes — applied globally across all chapters, not per-chapter,
  so an item whose real span crosses a chapter boundary no longer collides with a neighboring
  chapter's own content.
- Visually distinct colors per tier (chapter/era/period/polity/civilization-culture), a
  persistent left-margin gutter with a rotated tier-name label per row-block ("Epoch"/
  "Chapter"/"Era"/"Period"/"Civilizations & Cultures"/"Polities"), and separator lines whose
  style encodes scale: solid between tier row-blocks, dashed between region/continent
  sub-groups within one row-block.
- Auto-generated continent-split placeholder eras (from `generate_modern_regional_eras.py`)
  are hidden from the era row entirely — they carried no real historical distinction beyond
  restating the parent chapter, and duplicated it visually.
- Left-margin tier labels ("Epoch"/"Chapter"/.../"Polities") now anchor near the top of their
  row-block instead of the vertical midpoint, so a tall block's label is visible without
  scrolling to find it.
- A detail panel on click (`web/explore_details.js`), matching `/`'s own panel but read-only:
  dates, authority, geography, related-record links (with click-through cross-navigation
  between periods and polities), external links (Wikidata/DBpedia/source URLs), and a "Zoom to
  this" action reusing the existing zoom mechanism. Click now opens the panel instead of
  zooming immediately (zoom moved into the panel's own button) — matches `/`'s own
  click-opens-panel interaction rather than /explore's earlier click-to-zoom-directly behavior.
  No editing actions (`/` keeps those as curation tools; `/explore` is a browse view). Verified
  live in a real browser: chapter/era/period/polity/civilizations-lane bands all open the
  correct panel content, cross-navigation and zoom-then-reset both work, zero console errors.

See [ROADMAP.md](ROADMAP.md) for what's still queued on `/explore` — moved there since it's
forward-looking, not retrospective. See the "geography-grouping unification" section below for
the current (31 August) state of grouping/coloring — it superseded the four-option toggle and
curated/heuristic legend described in earlier drafts of this section.

**Known, accepted limitations:**
- `MAX_POLITIES_PER_REGION = 15` caps each geography bucket's shown bands with no visual
  "+N more" affordance — the true count is only visible via tooltip.
- Most of `explore_tree.json`'s era/period/polity placements are heuristic (geography+date
  overlap), not curated — `period_links.yaml`/`broader_periods` coverage is still thin. This is
  by design (the alternative was an empty page) but means placement quality varies.

### `/explore` geography-grouping unification, era-linked colors, and dataset cleanup — 31 August 2026

Driven by the same live-testing-on-the-running-page process as the section above, on branch
`explore-unified-geography-grouping`.

**Grouping unified across rows:** the Period, Polities, and Civilizations & Cultures rows now
share one client-side geography-grouping implementation (`geoBucketKey`/`continentGroupedLayout`/
`geoCountryGroupedLayout` in `web/explore_timeline.js`), replacing the old Polities-only
four-option toggle (historical region/continent/country/hidden) and the Civilizations row's
separate always-flat layout. Two independent controls replaced it: a "Show polities" checkbox
(Civilizations & Cultures stays visible regardless of this checkbox — explicit correction after
an initial design merged the two rows, then un-merged them back per "in all cases I should see
the Civilization lane"), and a "Group by" selector with three modes — Continent (with an inline
"(Country)" label suffix when an item has exactly one `present_countries` value), Country (full
nested continent→country sub-headers), and None (flat, but still lane-packed in a
continent-then-country-then-date sort order — see `geoClusterSort` — so same-geography items
visually cluster even with no group headers drawn). A "Filter to" control (hidden in None mode)
narrows all three grouped rows to one continent/country at a time. The Asia-sub-split and
sort-adjacency behavior from the original continent-grouped rows carried over unchanged.
`pipeline/build_explore_tree.py` gained matching geography fields
(`primary_continent`/`primary_historical_region`/`present_countries`) on polity and civilization
entries (previously periods-only) to make this possible.

**Era-linked color coding:** periods (via a new `era_id` field, free from tree nesting) and
Civilizations & Cultures entries (via a new `linked_era_id` field, `_linked_era_id()` in
`build_explore_tree.py` — the same date+geography heuristic `rank_candidates` uses to place an
ordinary period without a curated `broader_periods` link) are colored to match their regional
era, so e.g. every Mesopotamia-related record reads as one visual group regardless of which row
it's in. Era bands get colors from the same palette, keyed by their own id. Assignment is by
sorted-index into an 18-color palette (not a hash — an earlier hash-based version collided
multiple unrelated eras onto the same color), built once from the full, unzoomed tree so colors
stay stable across zoom/filter.

**Placement legend retired, dash/solid repurposed:** the curated (sourced link) vs. heuristic
(date/geography guess) distinction — previously shown as solid vs. dashed borders across every
row, with its own "Placement" legend — was retired as a visual signal (explicit request: "get
rid of the placement visual cue"). The same dashed/solid channel is reused, scoped to the
Civilizations & Cultures row only: solid = plain polity, dashed = civilization/culture/people/
tribe entry. The legend now reflects this ("Style: Polity (solid) / Civilization, culture,
people, or tribe (dashed)").

**Mesopotamia reclassification:** `mesopotamia_period.yaml` (new, `authority:
'Histomap editorial: civilization-as-backdrop'`, mirrors `ancient_egypt_period`) now carries the
Civilizations & Cultures lane's weight for the region. Sumer, Akkadian Empire, Uruk (an existing
polity, previously excluded from `/explore` by `visibility_tier: detailed` with no override — the
same gap the original Sumer visibility fix addressed), and Babylonia (new `polities/babylonia.yaml`,
replacing the deleted `babylonia_period.yaml`) are now plain polities — reversing the Akkadian
Empire/Uruk elevation and Sumer's culture classification from the prior section, on explicit,
direct instruction. `mesopotamian_early_states_era` (the regional_era) is unchanged, still anchors
Early Dynastic Mesopotamia's placement in the ordinary Period row.

**`egyptian_early_states_era` deleted outright** (not demoted) — redundant with
`ancient_egypt_period`, and nothing else nested under it (no period pointed `broader_periods` at
it, and no Egypt-specific period records existed to heuristically match it either). One side
effect: `ancient_egypt_period`'s `linked_era_id` heuristic now resolves to `neolithic_era` (its
next-best geography/date match) instead of a dedicated Egypt era — cosmetic, flagged but not
fixed.

**New overarching regional eras**, same "overarching regional era" pattern as
`bronze_age_era`/`neolithic_era`/`paleolithic_era` (see ONTOLOGY.md): `iron_age_era` (reparents
`european_iron_age` and `sub_saharan_african_iron_age_era`, previously unrelated to each other —
one heuristically nested under Mediterranean Classical Antiquity, the other its own standalone
regional_era), `copper_age_era` (new — no periods reparented under it yet; flagged transparently
in its own notes rather than fabricating a period record to fill it), and
`classical_antiquity_era` (reparents `mediterranean_classical_era`, `east_asian_classical_era`,
`south_asian_classical_era`, `mesoamerican_formative_classic_era`, and
`andean_early_civilizations_era` — deliberately excludes Sub-Saharan Africa, whose equivalent is
`iron_age_era`, not a "classical antiquity").

**Smaller fixes along the way:** `celts_period.yaml` → `polities/celts.yaml` (`entity_type:
people` — never a single political actor, per the deleted period record's own prior notes);
ROADMAP.md's "Ideas" section gained a "main events lane" entry (events that define an
era/chapter/period's start/end, currently only implicit in `start`/`end` dates).

**Kingdom/crown/house audit — closed, nothing left to convert.** The remaining ROADMAP item asking
to "check for any other kingdom/crown/house-named periods still needing the [period→polity]
treatment" turned up 11 period records still named "Kingdom"/"Republic" (`albanian_kingdom_q1048340_period`,
`czechoslovak_republic_period`, `second_spanish_republic_period`, etc.) — but every one of them
already carries a reviewed `period_links.yaml` `phase_of` relation to its canonical polity
("Reviewed record is a dated phase of this canonical polity", high confidence), the same
deliberate context-band-under-a-continuously-existing-polity pattern as the House of
Wessex/Plantagenet/Tudor precedent this item's own text already called out as correct-as-is.
Removed from ROADMAP.md.

### `/explore` side panel editing, and review workspace alignment — 31 August 2026

Investigated (see agent report, not reproduced here) whether the review workspace still let a
reviewer reclassify an entity (era/period/civilization/polity) with links staying consistent, per
ROADMAP item 1. Findings: `entity_type` reclassification was well-built and reachable from
`/reviews` → `/type-review`. `tier` (macro_chapter/regional_era/period) had zero UI and zero API
endpoint anywhere — hand-edit-YAML only, exactly the workaround the geography-grouping unification
section above needed throughout. Polity↔Period conversion existed but was split: Period→Polity
("promote to entity") was link-consistent but only reachable from `/` (Timeline), not `/reviews`;
Polity→Period (the consolidation queue's "period" decision) was reachable from `/reviews` but only
covered `timeline_role: "period"`, not `"both"`. `/period-review` (a dedicated period-role review
page) was already orphaned — 307-redirecting to `/consolidation-review` — with its one useful
decision already duplicated via consolidation review's own `P` shortcut.

**Resolution, on direct instruction ("I need to be able to edit things via the side panel. The
review section should just be corrected so that it works in the new context"):**

- **`/explore`'s side panel (`web/explore_details.js`) gained editing.** No longer read-only: an
  "Edit" section on every polity/period panel offers (a) the same single-field actions `/`'s own
  drawer already has (set entity type, set period type — reusing the existing, already link-
  consistent `PATCH .../entity-type` and `PATCH .../kind` endpoints) and conversion actions
  ("Convert to period" / "Convert to entity", reusing/adding endpoints below), and (b) a general
  "Edit fields" raw JSON editor covering anything else in the record with no dedicated control
  (`tier`, `broader_periods`, dates, `weight_by_era`, ...) — the actual gap behind the hand-edit-
  YAML pattern. The chart's bands (which row/lane something renders in) come from the separately
  pre-built `explore_tree.json`, not the live-editable `politiesById`/`periodsById` maps these
  edits update — every save says so explicitly, since it only takes effect after the next build.
- **New endpoints:** `POST /api/polities/{id}/convert-to-period` (direct, ungated counterpart to
  the existing `promote-to-entity`, wrapping the same `save_timeline_role` helper the consolidation
  queue uses; a `keep_entity` flag selects `timeline_role: "both"` instead of `"period"`, preserving
  the one capability that was otherwise only reachable through the now-retired `/period-review`).
  `PATCH /api/polities/{id}/fields` and `PATCH /api/periods/{id}/fields` — general-purpose editors:
  merge submitted fields onto the existing record, validate against the full `Polity`/`Period`
  schema before writing (422 on failure), track real changes in `manual_overrides` by comparing
  *normalized* (schema-defaulted) values on both sides rather than raw dicts — the panel's raw
  editor round-trips through the fully-expanded `/data.json`/`/periods.json` model dump, so a field
  a human never touched (e.g. `tier`, implicit via its schema default in the hand-authored YAML)
  would otherwise falsely register as "changed" the moment it becomes explicit in the submission.
  `id` can never be changed through either endpoint (would desync the record from its filename).
- **`/period-review` retired outright**, not fixed: removed the page route, `web/period_review.html`/
  `.js`, and the `/api/period-role-reviews` GET/POST endpoints + `TimelineRoleUpdate` model. The
  underlying `period_role_queue`/`refresh_period_role_queue` machinery stays — the consolidation
  review queue's own "period" decision still reads `period_kinds` from it to pick the created
  period's `kind`.
- Verified live: entity-type change, "Convert to period", and raw-field save all round-tripped
  correctly through a running server (each test reverted via `git checkout` afterward); 422 on
  invalid `entity_type`; `manual_overrides` stayed exactly `["notes"]` for a single real change,
  confirming the normalized-comparison fix. 243/243 tests pass.

Merged to `main` (fast-forward, `aeef81c9`). ROADMAP item 1 removed as closed by this work.

### `/explore` geography editor, transitions view, Makefile trim, and more live-testing fixes — 31 August 2026

Continued live-testing after the merge above surfaced more fixes, a live-testing feedback batch of
data reclassifications, and closed two of ROADMAP item 0's blocking gaps.

**Continent-mode lane packing fixed:** `continentGroupedLayout` used to lane-pack a whole continent
bucket's items together, so two different countries' items could land in the same lane whenever
their dates didn't overlap (unlabeled "Old Kingdom" sharing a row with "Kingdom of Aksum
(Ethiopia)"). Now packs each present-day-country sub-group separately (no-clear-country groups
first, via `countryKeySort`) and stacks those lane sets — costs a few more lanes but keeps every
row visually one country at a time. Country mode was already correct; only Continent mode needed
this.

**Data reclassifications**, all via the new side-panel convert/fields endpoints or direct YAML
edits, each reviewed individually: Han dynasty (deleted — its `phase_of` link pointed at the wrong,
unrelated "Han" state, Q1574130 vs. the real dynasty's Q7209; `western_han`/`eastern_han` polities
already cover it correctly), Tibet under Yuan administrative rule and 5 Commonwealth realm records
+ Union of South Africa (period → plain polity), East Punjab (period → subdivision polity, parent:
`punjab`), 29 more modern-era `phase_of`/`part_of_periodization` companion periods from Early
Modern Global Connections onward (Russian Empire, German Reich, Nazi Germany, Czechoslovak
Republic, etc. — spot-checked every target for a Han-style mismatch first, none found), Elam and
Pyu city-states (civilization → polity), Viking Age (routed to civilization level via the same
explicit `civilization-as-backdrop` authority marker as Ancient Egypt/Mesopotamia/Chinese Empire),
Mesopotamian Early States era (deleted outright as a duplicate of `mesopotamia_period`, same
treatment as Egyptian Early States earlier), Norwegian Jarldom of Orkney (geography fix — had
Antarctica as a continent and Norway instead of the UK as present-day country). Two conversions
that appeared without a traceable request (`nationalist_zone_period`, `spain_under_joseph_
bonaparte_period` — likely the user's own side-panel testing) were caught and reverted cleanly,
including restoring their `period_links.yaml` entries verbatim from HEAD.

**"Build timeline" button** added to `/explore`, reusing `review_build.js` (already shared by
`/reviews`) — same `/api/actions/build` polling, no new server code. Starts hidden; every
successful side-panel save (via a new `ctx.onEdit` callback) reveals it, since `explore_tree.json`
is a separate pre-built artifact and a side-panel edit has no visible effect on the chart until a
build runs.

**ROADMAP item 0's two blocking gaps closed, same day as the audit:**
- **Geography editor** in `/explore`'s side panel (polities only), closely mirroring `app.js`'s
  `geographyEditorMarkup`/`syncContinentsFromCountries`/`saveGeography` — continent checkboxes,
  primary-continent select, filterable present-country checklist with continent auto-inference.
  Found and fixed a real bug in the shared `PATCH /api/polities/{id}/geography` endpoint along the
  way: every save silently dropped `historical_regions`/`primary_historical_region` (discovered via
  the Orkney fix above) — now preserves whatever was already there. New test:
  `test_geography_update_preserves_historical_regions`.
- **Transitions view**: `/explore` now fetches `/transitions.json` (previously never loaded) and
  shows a Transitions line (year, label, optional source link) on any polity that appears in a
  transition's `from`/`to`, matching `app.js`'s own inline treatment exactly.

ROADMAP item 0 updated to reflect the 2 closed / 3 remaining steps (non-blocking gaps, README/nav
updates, then the actual deletion) rather than treating retirement as still fully open.

**Makefile trimmed** to the daily-driver targets only (`setup`/`validate`/`build`/`serve`/`test`/
`format`/`lint`/`check`) — confirmed with the user that none of the ~24 one-shot pipeline/
extraction targets (`extract`, `extract-seshat`, `reconcile`, `apply-reviews`, `review`,
`compute-prominence`, `enrich-*`, `seed-regional-eras`, `suggest-*`, etc.) are still used day to
day. The underlying `pipeline/*.py` scripts are untouched — only the Make wrappers were removed;
README.md's "Wikidata backbone" section now shows only the direct-Python form of that sequence
(previously duplicated as both `make X` and the Python equivalent). ROADMAP item 1 removed as
closed.

244/244 tests pass throughout; every data change rebuilt and verified live in a running browser
before commit.

### `linked_era_id` made explicit, codebase-wide simplify pass, and JS dedup — 31 August 2026

**`linked_era_id` converted from heuristic to an explicit, editable field.** The
geography-grouping-unification section above's era-linked coloring relied on `_linked_era_id()`
recomputing a best-guess era match on every build, via the same `rank_candidates` heuristic used
for ordinary period placement — silently reshuffling depending on unrelated data changes
elsewhere in the set, with no way to correct a bad match short of fighting the heuristic (this is
exactly what surfaced Indus Valley Civilization not sharing Mesopotamia's color, and led to
finding a real bug: `bronze_age_era.yaml` carried a stray `historical_regions: [east_asia]`
left over from a demoted child era, blocking `geography_matches()`'s region-overlap preference
from ever matching non-East-Asian civ-lane items against it — every other overarching era
correctly has no `historical_regions` at all; fixed by removing the field). Per direct
instruction ("this link should be editable, not based on heuristic"): added `linked_era_id: str |
None` to both `Polity` and `Period` in `schema.py`, removed `_linked_era_id()` from
`build_explore_tree.py` entirely (both civ-lane entry builders now just read the stored field),
and added a new one-shot `pipeline/seed_linked_era_ids.py` (idempotent — only fills an unset
field) that seeded roughly 800 polities and 10 periods from the retired heuristic as a starting
point, so the transition didn't blank out existing coloring. The field is editable through
`/explore`'s side panel raw-fields JSON editor, same mechanism as any other field with no
dedicated control.

**Codebase-wide `/simplify` pass**, per direct request to look for dead code, convoluted logic,
and duplicated concepts across the whole codebase (dispatched to the `code-simplifier` agent, plus
follow-up decisions made directly against its findings):
- Deleted `pipeline/backfill_missing_geography.py` (373 lines, zero references repo-wide) and
  `pipeline/report_period_pilot.py` (54 lines, its one-shot report generator; the historical
  `reports/period_pilot_summary.md` it produced stays, same treatment as the backfill script's own
  historical reports).
- Removed `score_prominence()` (`pipeline/compute_prominence.py`) and `aggregate_radius()`
  (`pipeline/extract_hyde.py`) — both superseded functions kept alive only by their own tests;
  deleted alongside their tests.
- Introduced `CURRENT_YEAR = datetime.now(timezone.utc).year` in `schema.py`, replacing four
  independent hardcoded `2026` sentinels (`compute_prominence.py`, `generate_modern_regional_eras.py`,
  `reconcile.py`, `suggest_period_links.py`) that all meant "today, for an open-ended entity's
  current age" — a genuinely different concept from `YEAR_MAX = 2100`, the dataset's fixed
  modeled-timeline ceiling, which stays untouched and hardcoded on purpose.
- Trimmed `seed_regional_eras.py`'s 48-line per-row removal changelog comment down to a 7-line
  summary pointing at STATUS.md/git history instead.
- Fixed two live `web/styles.css` rules referencing undefined custom properties (`var(--line)` →
  `var(--rule)`; `var(--ink)` → a literal color, since `:root` never defines `--ink`).
- Investigated and deliberately left two things as-is, with reasoning recorded rather than
  changed: `review.html` still loads `review.js` directly rather than the shared
  `review_build.js` module the other `/reviews`-family pages use, because `review.js`'s build
  button shares `startAction`/`pollJob`/`setActionButtonState` machinery with a second, distinct
  "Apply review decisions" button that `review_build.js` has no equivalent for — consolidating
  would have risked a functional regression for a cosmetic win. The six Makefile targets the
  agent flagged as candidates for retirement were kept, also with reasoning recorded.
- Server-side (`server/app.py`): collapsed 7 near-identical page routes and 5 near-identical
  build-artifact routes into `register_page`/`register_build_artifact` loops; factored
  `save_merged_fields()` out from the two `/fields` endpoints and `write_period_record()`/
  `append_period_link()` out from `save_consolidation`/`save_timeline_role`.
- Frontend: consolidated `escapeHtml`, `displayTerm`, `svgEl`, and the four byte-identical
  `/reviews`-family `formatYear` implementations into a new `web/common.js`, a classic
  (non-module) script loaded first on every page. Both classic scripts (the `/explore` family)
  and ES modules (`app.js`, the `/reviews` family) reach its globals via normal JS scope-chain
  lookup with no page needing to change how it loads scripts. `app.js` keeps a local `const
  svgElement = svgEl` alias so its own call sites needed no renaming. Two `formatYear` variants
  were deliberately left alone as genuinely different, not accidental duplicates: `app.js`'s own
  (no null-handling — its callers never pass one) and `explore_timeline.js`'s own (adds
  locale-formatted thousands separators on top of the shared null/BCE/CE handling). Verified live
  via chrome-devtools: zero console errors on `/`, `/explore`, `/reviews`, `/consolidation-review`,
  `/type-review`, and `/subdivision-review`.
- Deleted dead CSS selectors the agent also flagged: the `.nav-menu` dropdown block (no
  matching markup anywhere) and `.empty`/`.score-breakdown` (both orphaned).

**Process note.** Dispatching the `code-simplifier` agent without worktree isolation, in the same
working directory as concurrent uncommitted edits, caused a `git stash`-based collision that
reverted an in-progress `bronze_age_era.yaml` fix and a `ROADMAP.md` edit — the agent itself
detected both as out-of-scope changes and reverted them cleanly at its own initiative rather than
silently keep them, preserving the reasoning in its final report; both were reapplied once it
finished. Separately, one commit message (`317655ab`) claimed four of the items above (the
`review.html` decision, `score_prominence`/`aggregate_radius` removal, the `seed_regional_eras.py`
comment trim) were done when they had only been planned — caught via direct `grep` verification,
corrected in the user-facing reply, and actually executed for real in the follow-up commit
(`5f3e1d57`) with an accurate message.

242/242 tests pass; every JS/CSS/pipeline change verified live before commit.

### Seshat unmatched-drafts import, stale-figure audit, and `/` retirement — 31 August 2026

**Stale-figure audit.** ROADMAP.md and STATUS.md had both drifted well behind reality — some
figures (test count, consolidation queue size, Seshat reconciliation status) had gone unrefreshed
for a long time, not just from this session's work. Re-measured everything live via the running
server's `/api/review-dashboard`/`/api/reviews` endpoints plus direct dataset/git counts; see the
"Current measurable state" section below for the corrected figures.

**Seshat unmatched drafts imported.** `reports/seshat_unmatched_drafts.yaml` (34 Seshat source
records that never matched an existing Histomap entity) had no consumer anywhere in the pipeline.
New `pipeline/import_seshat_unmatched_drafts.py` (idempotent) writes each as a minimal draft
`polities/*.yaml` and queues an honest `/type-review` entry for each (proposed_type
`archaeological_horizon`, confidence `low`, reason states plainly there's no automated Wikidata
evidence since these records have no Wikidata item at all). Two ids carried a literal `*` from
their Seshat NGA code (e.g. `IqEDyn*`); sanitized for the id while keeping the original code in
`external_ids.seshat`. Also recomputed `prominence_score` dataset-wide while at it (hadn't run
since before this session's period→polity conversions, so ~70 records had stale or
never-computed scores).

**`/` retired.** Direct decision: any `/`-only feature not already on `/explore` (free-text
entity search, visibility-tier/entity-type/period-kind filters, the named-period picker + `?era=`
deep link, era presets/manual date-range input, relationship highlighting on the chart, swimlane
collapse/expand, keyboard-operable bands) is an accepted loss, not ported — simpler than building
parity first. Deleted `web/index.html`/`web/app.js`; removed the `("/", "index.html")` page
registration in `server/app.py` and added a 307 redirect from `/` to `/explore` instead (so
bookmarks/typed URLs still land somewhere useful, rather than 404ing); the pre-existing `/web` ->
`/` legacy redirect now points at `/explore` too. Every remaining page's nav dropped the
"Timeline" link and repointed the brand-logo link from `/` to `/explore`;
`type_review.html`'s "Open timeline" button relabeled "Open Explore." README.md's quickstart
rewritten around `/explore` as the primary workspace. New test `test_root_redirects_to_explore`;
discovered and fixed a real gap while at it -- `/explore` had no page-serving test coverage at
all before this (the old test only checked `/`). Verified live via chrome-devtools: redirect
confirmed both via curl and in-browser, nav renders correctly, zero console errors across
`/explore`, `/reviews`, `/type-review`.

243/243 tests pass throughout.

### `/review` (Seshat reconciliation) removed — 31 August 2026

Considered removing the whole review workflow, since its main historical role was importing
Wikidata/Seshat data. Pushed back on the full-removal framing: `/consolidation-review`,
`/type-review`, and `/subdivision-review` aren't import gates -- they curate the canonical set
that already exists, independent of any future import, and had real backlogs (832/3,098/2
pending) that would have had nowhere to go without them. `/review` (the interactive Seshat
source-vs-candidate matching UI specifically) is genuinely different: import-specific, and its
queue was already fully cleared (0 pending, confirmed live). Direct decision: remove `/review`,
keep the other three.

Removed `web/review.html`/`web/review.js`, the `/review` page route, `GET /api/reviews`/
`POST /api/reviews/{seshat_id}`, `ReviewDecision`, `add_source_links()`, and the
`review_queue`/`reviews_by_id` state (with its `pending_records()`/`save_decision()` plumbing
from `pipeline/review_cli.py`). Kept `pipeline/reconcile.py` and
`pipeline/apply_review_decisions.py` as scripts, and their `ALLOWED_ACTIONS` entries as
API-triggerable hooks (`POST /api/actions/reconcile`, `/api/actions/apply-reviews`) -- reusable
groundwork if source data ever needs reconciling again, without rebuilding a dedicated review UI
first. `refresh_review_queue()` simplified to `refresh_metadata()` (just reloads
`polities/*.yaml`), still wired to run after a `reconcile` action completes.
`web/reviews.js`/`.html` and README.md updated to match. Verified live: `/review` 404s,
`/reviews` renders 3 tiles (was 4) with correct counts, zero console errors. 239/239 tests pass
(four tests exercising the deleted endpoints removed along with their fixture data).

### Wikidata type-eligibility and entity-type rules-table expansion — 31 August 2026

Asked how to automate the 1,948-flag type-eligibility backlog and the 3,098-pending entity-type
queue. Unlike the consolidation queue (a genuinely unreliable fuzzy-match heuristic, see the
section above), these turned out to be a fundamentally different, much safer kind of gap:

- **The report itself was stale.** `Q188443` (micronation) was already accepted in
  `pipeline/wikidata_types.toml`'s rules, but `reports/wikidata_type_decisions.jsonl` predated
  that edit and still showed the old verdict for every record carrying that type -- 101 records
  resolved for free just by re-running the existing pipeline with zero rule changes.
- **98% of the rest (1,909 of 1,948) weren't ambiguous at all** -- they were Wikidata direct
  types (`P31`) that had simply never been added to the rules table (`classify()`'s "no direct
  allow or deny type" fallback). Pulled the ~80 most common unmapped types and looked up what
  each actually is: almost all turned out to be unambiguous historical polity types --
  principality, duchy, sultanate, khanate, protectorate, vassal state, colony, satrapy, taifa,
  bantustan, historic Chinese/Italian/German states, and similar -- that nobody had gotten around
  to classifying. Unlike judging whether two specific records are the same entity (context-
  dependent, exactly what went wrong with the consolidation queue), classifying a *type*
  ("does 'principality' mean polity-eligible?") is a stable, one-time, auditable judgment.
- Added **45 QIDs to `[allow].strong_qids`**, **7 to `[allow].contextual_qids`** (civilization,
  culture, archaeological culture, ancient civilization, ethnic group, historical ethnic group,
  free imperial city), and **4 to `[deny].qids`** (historical period, pre-Columbian era, "style,"
  noble title -- genuinely not polities, just mismapped into the candidate set) in
  `pipeline/wikidata_types.toml`. Deliberately left modern administrative subdivisions (US/
  Indian/Nigerian/Mexican/Venezuelan/Russian/Swiss/Malaysian/Australian/South Sudanese state,
  Canadian province, German federated state) unmapped -- the rules already route those to review
  on purpose, matching the existing `/subdivision-review` workflow, and this pass didn't
  second-guess that. Also left a handful of generically ambiguous types ("region," "historical
  region," "cultural region," "disputed territory") and a few Wikidata items with no English
  label in review rather than guess.
- Mirrored the same 45 polity QIDs (plus the 2 civilization/people additions) into
  `pipeline/backfill_entity_types.py`'s `TYPE_QIDS`, since that dict independently drives the
  entity-type classification queue -- most of the 3,098 pending there were only "medium"
  confidence because they were inferred through Wikidata's `P279` subclass ancestry rather than
  matching a recognized type directly; adding these as recognized roots upgrades many of them
  from ancestry-guess to direct-match, which resolves them (only non-"high"-confidence records
  stay queued).
- User pushed back usefully mid-review: these are all conceptually *sub-types* of polity
  (sultanate vs. khanate vs. duchy), and asked whether that should be structured rather than
  flattened. Confirmed neither rules table has anywhere to record that distinction today --
  `entity_type` is a flat 8-value enum, same as how `empire`/`kingdom` already collapse to plain
  `polity` -- and added a ROADMAP.md "Ideas" entry for a future `government_form`/`polity_subtype`
  field rather than solving it inline.
- Re-ran `pipeline/filter_wikidata_types.py --offline` (eligibility: 1,948 -> 661 still flagged
  across canonical `polities/*.yaml`) and `pipeline/backfill_entity_types.py` (entity-type queue:
  3,098 -> 2,682 pending, confirmed live via `/api/review-dashboard` after a server restart) and
  `pipeline/compute_prominence.py` (relationship counts shifted for many newly-typed records).
  Spot-checked several reclassified records live (Aceh Sultanate, Principality of Aigues-Mortes,
  Senarica -> all correctly `entity_type: polity`, confidence `high`, `eligibility: accepted`).
  239/239 tests pass; build validates cleanly (4,697 entities); zero console errors on `/explore`
  and `/reviews`.

### Name-matched present_countries fix, and a real consolidation-queue false positive caught live — 31 August 2026

While live-testing `/consolidation-review`, caught a concrete example of exactly the unreliability
documented in the earlier consolidation-queue investigation: a "high confidence" suggested match
between two "Peruvian Republic" records (`peruvian_republic_q116847047`, 1837-present, and
`peruvian_republic_q28517256`, 1838-1839) that are genuinely two distinct polities at different
times, not duplicates -- exact same shape as the earlier Roman Republic/Ancient Rome and East
Punjab/Punjab false positives. Correct decision: independent, not same_entity. Also noticed the
candidate's own `present_countries` was empty despite obviously being Peru; fixed by hand.

That specific fix led into a broader pass on ROADMAP item 6's residual gap: polities with no
continent/country from any automated signal (P17, direct P30, centroid) where the country is
often obvious from the record's own name. New `pipeline/seed_present_countries_from_name.py`
(idempotent) matches `canonical_name` against a conservative demonym/country-name table,
whole-word only, restricted to `entity_type: polity`. Found and fixed a real systematic risk while
building it: colonial/great-power adjectives (Dutch, Austrian, Italian, Portuguese, Belgian,
Spanish, Danish, Swedish, Russian, Chinese, Japanese, American, Ottoman) describe a foreign
power's *control* over a territory as often as they describe that power's own homeland -- an
early version matched "Dutch Loango-Angola" to the Netherlands, "Austrian Netherlands" to Austria,
"Italian Ethiopia" to Italy, and "Portuguese Cochin" to Portugal, all wrong. Fixed with two rules:
a colonial adjective loses to any other distinct-country match in the same name, and a colonial
adjective with no corroborating match is excluded entirely (no way to tell "colonizer's own home
front" from "foreign holding" from a name alone). Also excludes names matching two distinct
non-colonial countries at once (e.g. "Croatia in personal union with Hungary").

Dry-ran first (a separate scratchpad script printing the full match list grouped by country) and
reviewed every match by hand before applying anything, rather than trusting the heuristic blind --
same discipline as the consolidation-queue investigation that started this thread. Applied 146
matches, then ran `pipeline/derive_historical_regions.py` to complete the chain (142 of 146 got a
real `historical_region`; 4 remain in the still-tracked country-not-in-starter-table gap).
Continent gap: 986 -> 917; country gap: 672 -> 607.

239/239 tests pass; build validates (4,697 entities); zero console errors live on `/explore`.

### Comprehensive polity → period reclassification scan — 31 August 2026

Closed ROADMAP's "run a comprehensive scan across the full polity set, not just the 94-record
seed" item. `pipeline/classify_period_roles.py` already scanned every polity for one signal
(Wikidata's own period-type ancestry, auto-converting the unambiguous cases and queueing the
mixed ones) -- re-running it, now benefiting from the entity-type rules expansion above, found
the queue essentially unchanged (94 -> 80 candidates), meaning the original seeding wasn't
actually missing much on that signal.

Added a second, independent candidate source directly addressing the item's other half: a record
already classified `entity_type` civilization/culture/people/tribe/archaeological_horizon (a
context-type, not a weight-bearing political actor by the project's own convention) but still
modeled `timeline_role: entity`. Found 23 (Babylonia, Maya civilization, Gaelic Ireland, Xiongnu,
Hephthalites, and others). Deliberately not auto-converted, even though most already carry a
confirmed `entity_type` manual override -- that override only confirms the *kind* of thing,
not whether it should be period-vs-entity modeled; Babylonia is a documented case from earlier
this session of "confirmed civilization, deliberately kept weight-bearing." Queued into the same
`period_role_review.jsonl` mechanism for the existing human period/both decision in
`/consolidation-review`.

period_role queue: 80 -> 103 total; live `/consolidation-review` "active" count 75 -> 98 pending.
Verified live: Babylonia and the others render correctly with the new reason text
("entity_type is civilization, not a weight-bearing political actor by convention, but still
modeled as timeline_role: entity"), zero console errors. 239/239 tests pass; build validates
cleanly.

### Consolidation-queue alias-collision bug fixed; centroid and Wikidata-parent signals added — 31 August 2026

The Peruvian Republic false positive above, plus a second live example (Free City of Danzig,
two distinct polities 130 years apart sharing a name, correctly resolved `independent` the same
way), prompted trying to generalize "same name, non-overlapping dates -> independent" into an
automated pass. Doing so via the queue's own `exact_name_match` flag surfaced ~62 candidates
including clearly unrelated pairs (Dutch Brazil<->Australia, State of Qi<->Chile, Vatican
City<->Papal States, Romanov Empire<->Russian Empire, Mughal Empire<->India). None were applied --
root-caused instead to a real bug in `server/app.py`'s `consolidation_names()`: it collected every
alias/translation string with no minimum length, so "New Holland" (a name genuinely used
historically for both Dutch Brazil and colonial Australia) and the 3-character collision between
State of Qi's alias "Chi" and Chile's alias "CHI" both counted as an "exact name match" -- a signal
strong enough to bypass the geography/date gate entirely and inflate confidence to "high".

Fixed by requiring alias-sourced strings to be >= 6 normalized characters to count as a match
signal (mirroring `consolidation_tokens()`'s existing >= 4 convention); `canonical_name` itself is
always included regardless of length, since two records sharing it verbatim is meaningful even
when short. Also added two corroborating signals independent of name matching, per the specific
ask to use Wikidata fields like a parent or shared coordinates rather than names alone:

- **Centroid distance** (`geography.centroid`, already derived per-record): an alias match no
  longer auto-qualifies a candidate when the two centroids are >1500km apart, and confidence can't
  reach "high" in that case either -- it's now surfaced as a reason line ("centroids ~Nkm apart")
  rather than silently ignored. Centroids within 300km add a small score bonus and a "same
  location" reason.
- **Shared P131** ("located in the administrative territorial entity") target between the two
  Wikidata items, read from the already-cached `sources/wikidata_relationships.json` (no new
  fetch needed) -- a small corroborating bonus when both records are documented as sitting inside
  the same administrative entity.

Verified live: Dutch Brazil<->Australia and Qi<->Chile no longer appear as candidates at all;
legitimate matches sharing those tokens (Socialist Republic of Chile->Chile, Western/South
Australia->Australia) remain, scored via genuine token/geography signals rather than the alias
bug. Re-checked the Danzig/Limburg pattern (exact canonical name, non-overlapping dates, distinct
Wikidata items) across the corrected queue: zero remaining candidates -- the ~62-candidate list
was entirely a byproduct of the alias bug, not a real backlog, and both genuine instances found
this session were already resolved by hand. `/consolidation-review` "active" pending count:
827 -> 777 (entities whose only signal was the buggy exact-name-match now have no candidates at
all). 239/239 tests pass; build validates; zero console errors live.

### Six phase_of consolidation candidates resolved — 31 August 2026

Caught live on `/consolidation-review`: Syrian Arab Republic (1963-2024) suggested against Syria
(1920-present) as "high confidence" -- unlike the alias-collision false positives above, this one
is genuine (Syria's own Wikidata aliases legitimately include its official name "Syrian Arab
Republic") and structurally an obvious phase relationship, not a duplicate: target dates fully
contain source, present-day geography matches, entity types are compatible. Resolved as `phase_of`
Syria via the existing API, then scanned the corrected queue for the exact same pattern
(`date_contains` + `geography_match` + `type_match` + `confidence: high`) and found 5 more, each
checked against known history before applying:

- United Provinces of Central America (1823-1824) -- renamed Federal Republic of Central America
  in 1824
- Miguel Iglesias government (1882-1885) -- a specific administration within the Peruvian Republic
- Udaipur State (1818-1948) -- the colonial-era name for the same Kingdom of Mewar dynasty
- State of Greater Lebanon (1920-1926) -- the initial polity name under the French mandate of
  Lebanon
- Government of National Salvation (1941-1944) -- Nedic's collaborationist administration under
  German military occupation, exactly coinciding with the Territory of the Military Commander in
  Serbia

Each `phase_of` decision retires the reviewed polity record and rewrites it as a dated period
nested under its canonical target via `period_links.yaml` (existing behavior, not new). `build.py`:
4649 -> 4643 entities, 90 -> 96 periods, 17 -> 23 period links. `/consolidation-review` "active"
pending count: 777 -> 770. 239/239 tests pass; zero console errors live on `/explore` and
`/consolidation-review`.

### Wikidata succession links: relationship re-run, and a new consolidation-queue signal — 31 August 2026

Caught live: Batavian Commonwealth (1801-1806) suggested "high confidence" against Batavian
Republic (1795-1806) -- unlike the Syria-style cases above, this one turned out to be wrong.
Batavian Republic's own `aliases_en` carries a "Batavian Commonwealth" entry (genuinely >= 6
characters, so untouched by the earlier alias-length fix), but checking Wikidata's own P155/P156
("follows"/"followed by") data showed Republic -> Commonwealth -> Kingdom of Holland documented as
three distinct, sequential polities, not one entity under two names -- the same succession-chain
property type used for Roman Republic -> Roman Empire. Resolved `independent`; removed the
misleading alias from `batavian_republic.yaml` with a dated note explaining why.

That prompted two follow-ups, matching the explicit request to use "follow" links to both link
polities in the interface and assess identity/chronology automatically:

- **`pipeline/enrich_relationships.py` re-run.** This pipeline already existed to auto-apply
  successor/parent links from Wikidata's P155/P156/P1365/P1366/P361/P527 properties into the
  `successors`/`parent` fields `/explore`'s detail panel renders as "Followed by"/"Preceded by" --
  it just hadn't been re-run against the current, much-changed dataset (confirmed: it correctly
  added Batavian Commonwealth to Batavian Republic's `successors` once re-run). Doing so surfaced a
  real gap: the pipeline never checked `entity_type` compatibility before writing, unlike
  `build.py`'s own validator (successor requires polity -> polity; parent requires
  polity/subdivision -> polity). The first apply pass wrote 9 invalid links (Maya civilization
  given a "successor", Old Babylonian Empire given civilization-typed Babylonia as "parent", and
  others) and failed `build.py`. Manually reverted those 9, fixed the pipeline to filter on
  `entity_type` exactly like `build.py`'s validator (a new `type_conflicts` metric instead of a
  write), re-ran clean: 19 parents and 79 successors applied, the same 9 now correctly skipped.
- **New `documented_successor` consolidation-queue signal.** Mirrors the centroid-conflict signal
  added earlier: a shared P155/P156/P1365/P1366 link between two candidate QIDs now stops an alias
  match from auto-qualifying a candidate alone, keeps confidence from reaching "high", and is
  surfaced as an explicit reason instead of being silently folded into "exact canonical name or
  alias". Verified live: 119 candidates across the queue carry this flag (France/Kingdom of France,
  1st/2nd Syrian Republic, Fascist Romania/Kingdom of Romania, and similar genuinely-sequential-
  regime pairs), all correctly held at medium confidence.

Also resolved via `/consolidation-review` while investigating: Czechoslovak Republic (phase_of
Czechoslovak Socialist Republic, reviewed live in the browser), East Punjab and Ukrainian Soviet
Republic (both independent, reviewed live in the browser). `/consolidation-review` "active" pending
count: 770 -> 754. `build.py`: 4643 -> 4642 entities (one more phase_of retirement), 96 -> 97
periods, 23 -> 24 period links. 239/239 tests pass; zero console errors live.

### Consolidation queue now suggests the correct decision automatically — 31 August 2026

Two more candidates caught live needed the SAME reasoning as the Syria/Syrian Arab Republic case,
but in reverse: France (481-present, reviewed) vs. French First Republic (1792-1804, candidate) --
the REVIEWED entity is the broad continuous polity here, so the CANDIDATE is the one that should
become the phase, via the "Candidate -> phase of reviewed" direction. Same shape for German Reich
(1871-1949, reviewed, the official name spanning Empire/Weimar/Nazi Germany) vs. German Empire
(1871-1918, candidate, the specific monarchical phase). Both resolved correctly, but only after
manually checking date-nesting direction, entity types, and QIDs for each -- exactly the repeated,
mechanical work asked to be folded into the algorithm instead of re-derived by hand every time.

Added to `consolidation_review_queue()`:
- **`reverse_date_contains`**: the mirror of the existing `date_contains` -- catches the reviewed
  entity having the broader range, not just the candidate.
- **`possible_qid_conflict`**: a `same_wikidata` match whose dates diverge by more than a few years
  usually means one record has the WRONG Wikidata id, not a genuine identity match. Caught live:
  this dataset's Roman Republic and Ancient Rome both carry `Q1747689` despite covering different
  centuries -- previously surfaced as a misleading "high confidence" `same_entity` prompt. Now
  demotes confidence to medium, drops the `same_wikidata` score bonus, and surfaces an explicit
  "check for a misattributed Wikidata id" warning instead.
- **`suggested_decision`**: derived from the above plus the existing `documented_successor`/
  `coordinate_conflict` signals -- `same_entity` when `same_wikidata` genuinely lines up,
  `phase_of`/`candidate_phase_of` whichever direction the date-nesting actually points,
  `independent` when a documented successor or centroid conflict argues against identity, `null`
  wherever the evidence doesn't clearly point one way (an ordinary manual review, same as before).
  Live distribution across the queue: 445 `phase_of`, 179 `candidate_phase_of`, 134 `independent`,
  257 `null`.

`/consolidation-review`'s frontend (`web/consolidation_review.js`, `web/styles.css`) highlights the
matching button with a "Suggested" badge; the independent-only case (no per-candidate button exists
for it) gets an inline hint pointing at the page-level "Independent entity" control. Verified live:
West Virginia's "Reviewed -> phase of candidate" button correctly carries the badge; Roman Republic
now shows medium confidence with no suggestion and the misattributed-QID warning instead of the
previous misleading high-confidence prompt. 239/239 tests pass.

**Follow-up, same day: generalized the "name reused, different era" rule.** Bourbon Restoration in
France (1815-1830) vs. Kingdom of France (987-1791) still showed "high confidence" -- the same
Free City of Danzig/Duchy of Limburg shape from earlier this session (shared alias, distinct
Wikidata items, non-overlapping dates: the restored monarchy was genuinely called "Kingdom of
France" again, 24 years after the first record's own end date), but that rule had only been coded
as `documented_successor` (needs an explicit Wikidata succession edge -- this pair has none). Added
a broader `no_overlap_alias_reuse` signal: `exact_name_match` on two distinct Wikidata items whose
dates plain don't overlap, independent of whether a Wikidata succession edge exists. Demotes
confidence, drops the score bonus, sets `suggested_decision` to `independent`. Verified live:
Bourbon Restoration/Kingdom of France now correctly shows medium confidence with the independent
suggestion. Queue-wide: `suggested_decision="independent"` count 134 -> 172. 239/239 tests pass.

**Second follow-up, same day: date-containment tolerance, and requiring a real name match for
phase_of.** Two more issues caught live. First: Akragas (the ancient Greek city, 580 BCE-406 CE)
vs. its own continuous successor Agrigento (579 BCE-present, 3km away, same present country) showed
no suggestion at all, despite being an obviously clear phase_of case by inspection -- `date_contains`
required an exact `other.start <= document.start`, and a 1-year difference between the two records'
own start-year estimates (ordinary for ancient chronology) was enough to fail it. Added
`DATE_CONTAINS_TOLERANCE_YEARS` (10) to both `date_contains` and `reverse_date_contains`; verified
live, Akragas/Agrigento now correctly suggests `phase_of` (queue-wide: 445 -> 510). Also reordered
`candidateMarkup()` per direct feedback: the relationship buttons (with the Suggested badge) now
render before the "Why suggested" text, not after.

Second, more serious: West Virginia vs. Virginia showed "Reviewed -> phase of candidate" suggested
-- wrong, West Virginia seceded from Virginia in 1863 and both states have coexisted separately
ever since; it's a partition, not a phase of Virginia's own identity. The suggestion fired from
`date_contains` + `geography_compatible` + a shared "virginia" *token* (not a real alias match) --
the same shape `date_contains` alone was trusted for, on the assumption every previously-verified
phase_of case also happened to carry a genuine `exact_name_match`. Added that requirement
explicitly: phase_of/candidate_phase_of now also require `exact_name_match`. Confirmed the two
suggestions surviving the fix are genuine (Sharifian Empire's own alias is literally "Morocco";
Republic of Venice's aliases include "Venetian Empire", its maritime-empire period) -- not
coincidences, the requirement doing its job. Queue-wide this was a large, expected drop: 510
phase_of + 179 candidate_phase_of -> 2 phase_of + 0 candidate_phase_of -- most prior suggestions
were riding the same weaker token-only signal that produced the West Virginia false positive;
falling back to null (an ordinary manual review, same as before the suggestion feature existed) is
the right trade-off over surfacing suggestions this unreliable. West Virginia resolved
`independent`. 239/239 tests pass; zero console errors live.

### Queue counts refreshed live; ROADMAP trimmed to forward-only — 1 September 2026

End-of-session check requested ("check the roadmap and see if everything is up to date"). Confirmed
live via `/api/review-dashboard` and direct dataset counts, several figures had drifted from their
last-measured (31 August 2026) values after this session's consolidation-review work:
type-eligibility 661 -> 655, entity-type classification 2,682 -> 2,677, subdivision-parent 2 -> 1,
polity→period reclassification queue 98 -> 73, consolidation queue 1,617 -> 1,525 (all above updated
in the Phase 1 table and ROADMAP.md). `ROADMAP.md` item 0 (the phase_of/part_of merge) also had its
"done" half trimmed out in favor of a brief pointer here, per ROADMAP's own stated scope
("Forward-looking only") -- the full account already lives in this file's dated entries above and
below, so restating it there was pure duplication.

### Three more consolidation-queue signals, and a full review-UI pass — 1 September 2026

Continued live-testing the suggestion feature turned up three more signal gaps, each closed the
same way as before: a concrete counterexample first, then a signal generalized from it.

- **`likely_siblings`.** Canton of Appenzell Innerrhoden and Ausserrhoden -- both 1513-present,
  split from one original Appenzell canton -- showed no suggestion at all, despite being an
  obvious case by inspection. Distinct Wikidata items, different names, but *essentially
  identical* date ranges (both starting/ending together) is a distinct signature from ordinary
  date-containment: a true phase_of nests inside the continuous polity's own span with a
  *different* start; identical starts point to two things founded at once, not one being a phase
  of the other. Suggests `independent`.
- **`no_identity_signal`.** Kingdom of Wessex vs. Kingdom of Essex -- two different, coexisting
  Anglo-Saxon kingdoms of the Heptarchy -- reached the queue via geography + date-overlap + fuzzy
  name similarity alone (no shared Wikidata item, no shared name/alias), same shape as West
  Virginia/Virginia and the Appenzell cantons. Rather than patch each new instance of this shape
  one at a time, generalized it: whenever a candidate has no strong identity anchor at all,
  default the suggestion to `independent` -- the safer direction to be wrong in (a reviewer clicks
  past an overeager suggestion) versus leaving the common case unaddressed. Spot-checked a random
  sample of 6 of the resulting suggestions; all correct, including one pair (United Provinces of
  New Granada / Illyrian Provinces -- South America and the Balkans) that had matched purely on
  the generic shared word "provinces."
- **`regime_of_candidate`/`regime_of_reviewed`.** The `exact_name_match` requirement above also
  produced a real false *negative*: Federal People's Republic of Yugoslavia vs. Yugoslavia (a
  clear phase_of by inspection) stopped being suggested, because "Federal People's Republic of
  Yugoslavia" isn't a literal alias of "Yugoslavia" anywhere in the data. Added a naming-pattern
  check -- "`<regime type> of <the other record's name>`" (also matches Islamic Emirate of
  Afghanistan/Afghanistan) -- as an alternative to `exact_name_match` for the phase_of direction
  check, conservative enough that it doesn't reopen West Virginia (a compound place name, not this
  pattern, since "West Virginia" never reads as "West of Virginia").

Queue-wide after all three: `suggested_decision` distribution moved from mostly-null to
`independent: 924, phase_of: 76, candidate_phase_of: 4, null: 18` -- the queue had far more
"obviously distinct entities riding a coincidental partial match" than "obviously the same thing,"
once the algorithm could actually tell the difference.

Also root-caused a real, previously-worked-around bug: every "the button doesn't look updated"
moment this session traced back to `/static/*` files carrying no explicit `Cache-Control` header,
so browsers applied RFC 7234 heuristic freshness and could silently serve a stale JS/CSS file
after a deploy. Added a `Cache-Control: no-cache` middleware on `/static/*` -- forces revalidation
(still a cheap 304 when nothing changed) instead of a silent stale hit.

**Review-UI pass, same day, driven entirely by live use:**
- Removed the "Choose another parent polity" manual search section (dead weight once
  `suggested_decision` covers the common case) and the "Fast keyboard review" reference panel
  (redundant once every button shows its own shortcut inline).
- Fixed a real contrast bug: `kbd` had no explicit text color, so on a dark button it inherited
  white -- invisible against kbd's own white background. Now explicit dark text.
- Moved Independent/Discard/Defer from a single page-level block into each candidate card's own
  action row, so the Suggested badge -- previously usable only for same_entity/phase_of/part_of --
  now also highlights Independent. Confirmed live on the Appenzell and Wessex/Essex examples above.
- Added Wikipedia (English, falling back to whichever language edition exists) and locator-map
  (Wikidata P242) evidence rows, fetched in the same batch call already used for labels/
  descriptions.
- Added a two-row timeline bar (candidate vs. reviewed entity, shared scale) so date-containment
  is visible at a glance instead of read out of two separate table cells.
- phase_of/candidate_phase_of now disable with a tooltip -- instead of submitting and bouncing off
  a rejected-decision error -- when the relevant entity has no finite end date (a phase_of decision
  writes a Period record, which needs one). Caught live on Realm of New Zealand (open-ended) vs.
  New Zealand; the same guard already existed for the keyboard-shortcut path and the pre-existing
  "Broad period/era" button, just not for these two.

239/239 tests pass; zero console errors live beyond the pre-existing unrelated favicon 404.

**Layout redesign, same day, per direct feedback.** Trimmed the reviewed-entity header block to just
title + subtitle (the ID/Type/Dates/Present countries/Instance of/External page block below it
duplicated the "Reviewed entity" column every candidate card already shows), reordered the
comparison table to show Reviewed entity first with visual emphasis (bold, accent color) instead
of two visually-equal columns, and rebuilt each candidate card as two columns -- evidence on the
left, that candidate's action buttons stacked vertically on the right. Removed the sidebar
Progress card (pending-count moved inline under the page heading; decision-status moved to a
full-width banner under the toolbar) and widened the main column (74rem, up from 52rem) with the
freed space.

**Regime-of-place false positive fixed, same day.** Realm of New Zealand (1983-present) vs. New
Zealand (1841-present) showed no badge -- correct by accident (the phase_of button was separately
disabled for lacking a finite end date, which also hides the badge), but the underlying
`suggested_decision` was still wrong: "Realm of New Zealand" matches the regime-of-place naming
pattern, but here the Realm is the *broader* constitutional entity New Zealand belongs to, not a
phase of New Zealand's own history -- the opposite of the Yugoslavia case. The reliable tell: a
genuine regime-of-place phase is definitionally a completed episode (Federal People's Republic of
Yugoslavia ran 1945-1963); two still-open-ended entities matching the naming shape means the
"regime" side is more likely a container. Split the check: the raw naming match still counts as
identity evidence (the records plainly ARE related) but only drives a phase_of/candidate_phase_of
suggestion when the "regime" side has actually ended. Verified live: Realm of New Zealand/New
Zealand now correctly suggests nothing; Federal People's Republic of Yugoslavia/Yugoslavia and
Islamic Emirate of Afghanistan/Afghanistan (both finite-ended) still correctly suggest phase_of.
239/239 tests pass.

### Progress bar, one more phase_of gate, and a bulk-apply pass — 1 September 2026

Small UI follow-up per direct feedback: replaced the plain "N remaining" text with a thin progress
bar under the header (session-baseline percentage, since there's no fixed all-time denominator to
compare against) plus a small caption, moved the "This resolves..." explanation to sit as a
subtitle under the page heading, and reduced the review card's padding for a more compact display.

Asked to bulk-apply every "Reviewed -> phase of candidate" suggestion the queue produced, since the
ones reviewed by hand had all checked out. Fetching the full list (55 candidates) and sampling it
found the same clean pattern throughout -- specific historical regime name -> continuous modern
country or polity (Kingdom of Bulgaria/Bulgaria, the Afghanistan/South Korea/Venezuela/Prussia/
Albania/Republic of China regime sequences, ancient-city phases like Kingdom of Pergamon/Pergamon
and County of Edessa/Edessa). Applied all 55 via the API; 54 succeeded, 1 (Sharifian Empire/
Morocco) correctly bounced off the backend's "a phase/aspect requires a finite end date"
validation -- Sharifian Empire has a genuine "Morocco" alias but its own record is open-ended.

That failure revealed the same gap the Realm of New Zealand fix closed for `regime_of` still
existed for `exact_name_match`: the UI's disabled-button guard had been silently masking it (a
disabled button never carries the Suggested badge, so the bad suggestion was invisible in the
browser) but going through the API directly exposed it. Fixed the same way: phase_of/
candidate_phase_of now require the entity that would actually be retired to have a finite end date,
regardless of which signal is driving the suggestion. Verified live: Sharifian Empire/Morocco now
correctly suggests nothing.

Also caught and fixed a real data bug while resolving a separate live example (Alabama in the
American Civil War, flagged by the user as "supposed to be phase_of" but not suggested): its own
record had `end: null` (open-ended), wrong for a topical article about a war that ended in 1865 --
a Wikidata import artifact. Corrected to 1865 (`manual_overrides: [dates]`) and resolved as
phase_of Alabama.

build.py: 4633 -> 4572 entities, 106 -> 167 periods, 33 -> 94 period links (this batch plus several
further live decisions the user applied in their own browser during the same session).
`/consolidation-review` "active" pending count: 749 -> 688. 239/239 tests pass; zero console errors
live.

### Open-ended phase_of allowed; direct part_of signal; full review-UI overhaul — 1 September 2026

**Cursor fix, then a real capability request.** The mouse cursor showed "wait" (implying "try
again in a moment") on a permanently-disabled phase_of button -- fixed with a dedicated
`.ineligible` class and `cursor: not-allowed`. That surfaced the deeper ask directly: allow
submitting phase_of/candidate_phase_of even when the relevant entity is still open-ended. The
Period schema genuinely requires a finite end (`Period.end: int`, no `Optional`), so the backend
now approximates the missing end as the current year (low confidence, with a note explaining the
approximation) instead of refusing the decision -- a reviewer's judgment is worth more than that
structural gap. Removed the frontend's matching disabled-button/keyboard guards, since the backend
no longer rejects the submission.

**Direct part_of signal.** Live inspection of Realm of New Zealand vs. New Zealand's newly-added
"Part of" table row showed New Zealand's own Wikidata P361 claim names Realm of New Zealand
directly -- a much stronger, more direct signal than the existing shared_p131 (a shared
third-party administrative parent). Added `reviewed_part_of_candidate`/`candidate_part_of_reviewed`,
built from the already-cached P361 ("part of") and P527 ("has part") relationships -- no new
fetch. Drives a part_of/candidate_part_of suggestion directly (no finite-end gate needed, since
that decision writes a subdivision-parent link, not a Period record). 46 more candidates
queue-wide picked up a confident suggestion from this alone.

**Full review-UI overhaul**, driven by a long back-and-forth of direct live feedback:
- Progress bar repositioned to the toolbar/content boundary with a visible track (not just the
  fill), so it reads as an actual progress bar even near 0%, instead of a separate strip that
  blended into the page background at low fill.
- Table: dropped the redundant Histomap ID row; added Part of (P361) and Contains (P150) rows
  (same two-step Wikidata label-resolution pattern already used for `direct_type_qids`); reordered
  to Name / Instance of / Wikidata / Wikipedia / Part of / Contains / Type / Dates / [timeline
  bar, moved into the table as its own row] / Present countries / Locator map.
- "Why suggested" promoted from each candidate's own card into a bulleted banner above the
  candidate list for candidate 1 (the one usually carrying the Suggested badge).
- Buttons regrouped: Independent entity now sits with Same entity (both are "is this the exact
  same / totally unrelated" identity calls); Reviewed-> and Candidate-> direction buttons grouped
  with a divider between each cluster.
- **Keyboard shortcuts redesigned for AZERTY.** The user's own keyboard is AZERTY (French), which
  swaps Q<->A and W<->Z from QWERTY -- the original QWERTY-adjacent picks (Q W E R T / A D F G H /
  Z C V B N) landed on scattered, non-adjacent physical keys for an AZERTY typist, explaining an
  earlier "the shortcuts are a bit strange" comment. Redesigned around AZERTY's own row layout
  instead (A Z E R T / Y U I O Q for "Reviewed", D F G H J / W C V B N for "Candidate"), skipping
  K/P/S/X/digits already claimed by other shortcuts.
- Compactness: smaller heading, tighter margins around the card and candidate list.

239/239 tests pass throughout; zero console errors live beyond the pre-existing unrelated favicon
404. `/consolidation-review` "active" pending count: 688 -> 706 (more candidates now surface
correctly through the relaxed open-ended gate and the broader part_of inclusion criterion).

### Five more real cases fixed: institutional-name exclusion, geographic subdivisions, documented-relationship priority and pool inclusion — 1 September 2026

A further rapid-fire batch of real examples, each root-caused against the live signal data via the
API rather than guessed from screenshots this time:

- **"United States Army Military Government in Korea" was suggested phase_of "United States."**
  The name literally starts with "United States," but that names the army's *owner*, not a regime
  of the United States -- the real geographic anchor (Korea) is at the end. `name_is_regime_of()`
  now excludes a match at the very start of a name when immediately followed by an administrative/
  military noun (Army, Navy, Government, Administration, Command, Occupation, Mission, Legation,
  Corps, Authority, Garrison).
- **The demonym scan had a real bug**: "united" (a short common word) could prefix-match a
  completely unrelated multi-word name ("United Belgian States") via the wrong direction of the
  check. Restricted the demonym scan to single-word `outer_name` only -- demonyms are formed from
  single-word place names, not multi-word compounds.
- **"Scythia Minor (Crimea)" was suggested phase_of "Scythia."** "Minor" is a spatial qualifier
  (Asia Minor, Upper Egypt), not a regime/era qualifier -- entirely different semantics from
  "Francoist Spain." Added `name_is_subdivision_of_place()` (Minor/Lesser/Major/Greater/Upper/
  Lower/Inner/Outer next to a place name), excluded from regime_of evidence, wired into part_of/
  candidate_part_of instead.
- **Latvian Soviet Socialist Republic was suggested independent** despite a documented Wikidata
  P361 "part of" claim to Latvia AND exact date nesting, because it also has a documented successor
  ("followed by") relationship, and that branch was checked first, unconditionally. A "follows/
  followed by" claim alone usually does mean two distinct states, but a direct P361 claim to the
  *same* candidate is a more specific structural fact -- `documented_successor` no longer forces
  independent when `reviewed_part_of_candidate`/`candidate_part_of_reviewed` is also true.
- **A documented Wikidata relationship now adds the related entity straight into the candidate
  pool**, not just into scoring once already there. Previously an entity whose real documented
  successor/part-of target shared zero name/token overlap never got offered as a candidate at all
  (USAMGIK's real successor, "First Republic of South Korea," is a completely different name).
  **This is the single largest change in this whole rules-tightening arc**: live pending count
  jumped 590 -> 1,617, since many entities with a real documented relationship but no naming/
  geography overlap now correctly surface for review for the first time.

Also fixed a second real data error in the same family as Republic of Benin: USAMGIK's own
`present_countries` was recorded as US (the administering country) rather than KR (where it
actually operated) -- corrected geography/continents/historical_regions to match Korea. This was
also *why* "United States" matched in the first place (identical present_countries made geography
look compatible).

Six new regression tests, one per case above. 264/264 tests pass; zero console errors live
(caught and fixed the wrong-route verification bug in the process -- see the previous entry).

### Direct edit-fields panel added to /consolidation-review; regime-of-place naming now wins over documented_successor too — 1 September 2026

Two more live catches, right after the `detail_of` merge shipped:

**Editing capability.** Asked directly: "how can i edit entity?" Pointed to `/explore`'s existing
raw-fields editor, then immediately hit its real limitation live -- a queue entity (State of
Ecuador) wasn't easy to reach there. Added a proper fix instead of just a workaround: a new `GET
/api/polities/{id}` endpoint reading straight from server-side `metadata` (always finds an entity
regardless of publish/visibility status, unlike `/data.json`), a collapsible "Edit fields" raw-JSON
editor on every entity card in `/consolidation-review` itself (reviewed entity and every candidate),
saving via the same `PATCH .../fields` endpoint `/explore`'s editor already uses and reloading the
current queue item afterward so corrected data shows immediately. Also added an "Edit in /explore"
new-tab link and `?entity=<id>` deep-link support in `explore.js` (zooms to and opens the panel for
one record on load) for the fuller editing experience when an entity is visible there -- turned out
State of Ecuador actually did open correctly via the deep link too, just hard to spot visually in
the dense timeline; both paths work now regardless.

**`documented_successor` priority gap, second instance.** "Commonwealth realm of Mauritius"
(1968-1992) was suggested independent despite reading as "<regime> of Mauritius" with a finite end
and dates nesting exactly inside Mauritius's -- because Wikidata also documents a real "followed by"
relationship to Mauritius itself, and the existing fix (documented P361 claim wins over
documented_successor, from the Latvian Soviet Socialist Republic case) only recognized a direct
Wikidata part-of claim as the override evidence, not the regime-of-place naming pattern -- even
though that signal already carries its own finite-end safety gate, the same kind of "more specific
fact about this pair" the P361 exception already recognizes. `documented_successor` no longer forces
independent when `regime_of_candidate`/`regime_of_reviewed` is also true.

283/283 tests pass (2 new: `get_polity` success + 404; 1 new: the Mauritius regression case, using
real Wikidata data). Verified live: State of Ecuador's raw JSON loads/edits from the review card;
Commonwealth realm of Mauritius now correctly suggests `detail_of` Mauritius.

### Same-year start/end bug fixed: a real dissolution date was being read as "still exists" — 1 September 2026

Caught live via the consolidation-review page: "Inner Mongolian People's Republic" showed dates as
"1945 CE - present," even though it collapsed within two months of forming. The user's own
hypothesis was exactly right. Root cause: `pipeline/wd_to_yaml.py`'s `to_document()` silently nulled
any parsed dissolution year that was `<=` the inception year, and `schema.py`'s `Polity` validator
independently rejected `end <= start` -- but Wikidata records this entity's real inception
(1945-09-09) and dissolution (1945-11-06) as different dates that both round to the same calendar
year at year-level precision. That's a genuine short existence, not an error. Both checks now only
reject `end < start` (a real reversed-date data problem, still correctly nulled/rejected).

The same bug also affected ancient, poorly-documented entities where Wikidata records one single
approximate date for both P571 (inception) and P576 (dissolution) -- e.g. Hamazi:
inception == dissolution == -3000-01-01. Previously nulled to "still exists today" too.

Measured the blast radius before touching anything: 197 live records currently affected (`end: null`
but a real, recoverable Wikidata dissolution year), of which 196 were the same-year case and 1
(`amurru_kingdom`) was a genuinely reversed dissolution-before-inception -- correctly excluded, a
real Wikidata data problem rather than this bug. Added `pipeline/fix_same_year_end_dates.py`, a
one-off remediation recovering the real year from `sources/wikidata.parquet` (the cached raw
extraction still has the original value even though the imported YAML had it dropped), and ran it
against the real dataset: 196 records corrected, spanning ancient civilizations (Hamazi, Kizzuwatna,
...) through well-known modern short-lived states (Bavarian Soviet Republic, Baku Commune,
California Republic, Arab Federation, ...).

280/280 tests pass (17 new: 2 for `wd_to_yaml.py`, 2 for the schema validator, 6 for the remediation
script's fixture cases, plus the existing 5-question increment from this session's other work).
`build.py` validates clean. Verified live: Inner Mongolian People's Republic now shows `[1945, 1945]`
via the API, confirmed in the browser.

On the side question this also raised -- whether `/consolidation-review` needs its own inline
data-editing capability for cases like this: `/explore`'s side panel already has a raw-fields JSON
editor covering that need generically; confirmed with the user that's sufficient for now rather than
duplicating it into the review flow.

### phase_of and part_of merged into one detail_of relationship (ROADMAP task 0, data-model half) — 1 September 2026

Brainstormed (including a visual-companion mockup of the intended `/explore` reveal interaction),
designed, and implemented via `docs/plans/2026-09-01-detail-of-merge-design.md`. `phase_of`
(manufactured a synthetic Period record and retired the polity -- it vanished from the published
dataset) and `part_of` (retyped the polity to `entity_type: subdivision` and set `parent`) were two
structurally different mechanisms for the same underlying idea: "this entity is a detail of that
one." Replaced both with a single `Polity.detail_of: str | None` field -- a detail entity now stays
a live, published Polity with its own start/end/geography, exactly the shape a `part_of` subdivision
already had, just without needing to be retyped.

- **Schema**: `Polity.consolidation_status` drops `phase_of`/`part_of` from its `Literal` (keeps
  `independent`/`same_entity`/`discarded`); new `Polity.deprecated: dict | None` preserves every old
  field value under its original name, never deleted.
- **Backend**: `ConsolidationDecision` collapses four decision strings into two
  (`detail_of`/`candidate_detail_of`). `save_consolidation()`'s new `detail_of` branch just sets the
  field -- no Period creation, no entity_type retyping, no finite-end approximation (nothing left
  that needed one). `entity_type: subdivision` is now fully decoupled from this relationship,
  staying `/subdivision-review`'s own concern for genuine administrative subdivisions.
  `suggested_decision`'s naming/date/geography/documented-relationship signals are unchanged --
  only the output strings collapse.
- **Migration** (`pipeline/migrate_detail_of.py`, one-off): 164 `phase_of` records restored to live
  Polities (their generated `periods/*_period.yaml` + `period_links.yaml` row snapshotted into
  `deprecated`, then deleted from their live locations); 5 `part_of` records reverted to
  `entity_type: polity` with `detail_of` set from the old `parent`. Caught and fixed a real gap
  during the real run: reverting `entity_type` left stale `relationships[].kind` values
  (`administrative_part_of`, `cultural_sequence`) both on the migrated entities' own relationships
  and on *other* entities referencing them -- fixed by reusing `normalized_relationship_kind()`, the
  same rule a live manual entity-type edit already applies, across every polity's relationships.
- **Consolidation-review UI**: four buttons collapse to two (Reviewed/Candidate x
  detail_of); AZERTY shortcut keys collapse from four 5-key rows to two.
- **A mistake, disclosed**: an earlier migration attempt hit the relationship-kind bug above; fixing
  it required reverting the buggy attempt's output via `git checkout -- polities/ periods/ ...`
  before re-running cleanly. That revert also discarded 5 unrelated, uncommitted consolidation
  decisions that predated this work and had never been committed -- unrecoverable via git (never
  staged). Those 5 entities are simply back in the `/consolidation-review` queue as unreviewed;
  nothing else was affected. Lesson: check `git status` for anything beyond your own pending change
  before a broad `git checkout` on tracked-but-uncommitted paths.

270/270 tests pass (net new: schema validation, the migration script including the
relationship-renormalization case, updated consolidation-suggestion/server tests). Verified live:
`/consolidation-review` shows the two-button layout with suggestions working; `build.py` validates
clean (4,641 entities, up from 4,477, now that 164 formerly Period-only records are live Polities
again); Francoist Spain spot-checked directly in `data.json` -- `detail_of: "spain"`,
`timeline_role: "entity"`, full old Period/link snapshot under `deprecated`.

**Still open** (deliberately deferred, not part of this pass): the `/explore` display half -- hiding
a detail entity by default and revealing it via a badge/zoom-triggered enclosing panel. Today a
detail entity renders exactly like any other polity, an ordinary independent top-level band; not the
target end state, but not a regression either (every `phase_of` entity was previously invisible
outright, and every `part_of` subdivision already rendered as an independent band). See the design
doc's "Deferred: `/explore` display" section for what that follow-up design pass needs to cover.

### Regime-naming pattern generalized to any word-boundary placement, plus a timeline-axis label bug and a real data error found live — 1 September 2026

A rapid-fire batch of real examples, submitted live within minutes of the previous "Qualifier
Place" broadening, showed it wasn't nearly general enough: "Syrian Federation" (demonym as the
FIRST word, regime noun last), "Spain under the Restoration" (the exact place name literally
first, descriptor after), "First Brazilian Republic" (demonym in the MIDDLE of a three-word name),
"Bruneian Sultanate", "Socialist Republic of Chile", "Bolivian State", "Old Babylonian Empire", and
others all failed to match the first/last-word-only version. Replaced it with two general checks:
outer_name's exact words appearing anywhere in inner_name at a word boundary (covers prefix,
suffix, and mid-sentence placement uniformly with one substring test), plus a per-token demonym
scan (any single word in inner_name that's a literal prefix/suffix match of outer_name -- Syria/
Syrian, Brazil/Brazilian, Brunei/Bruneian -- catching regular "place + suffix" demonyms without a
full demonym dictionary; irregular ones like France/French still aren't caught). Same finite-end
safety rail as every previous round. Confirmed live via the four hardest of the batch, each added
as its own regression test. 259/259 tests pass.

**Timeline-axis label bug fixed.** The per-candidate timeline bar's right-edge label showed the
literal string "2100 CE" for any open-ended ("present") entity -- 2100 is only an internal cap used
for bar-width math, never a real date, so this was confusing rather than informative. Now reads
"present" whenever the entity reaching the right edge is itself open-ended.

**Real data error found and fixed, unrelated to the algorithm.** Republic of Benin's
`present_countries` was recorded as NG (Nigeria) with a Nigeria-based centroid, not BJ (Benin) --
likely confused during Wikidata extraction with the historical Kingdom of Benin, which really was
located in what's now Nigeria. Corrected to match the real Benin record's geography.

**Own verification-process bug caught and fixed.** All of this session's browser-based live checks
had been navigating to `/reviews/consolidation`, which doesn't exist (the real route is
`/consolidation-review`) -- silently loading a 404 JSON page instead of the actual review UI every
time. The functional fixes were still verified correctly throughout via direct API calls and the
user's own screenshots of the real page, but the "zero new console errors" claims from those
browser checks were about the wrong page. Corrected going forward; re-verified against the real
route with a genuinely clean console (not even the usual favicon 404 this time).

Applied roughly 46 more consolidation decisions live during this pass, mostly confirming the
naming-pattern fixes above end to end (Syrian Federation, Spain under the Restoration, First
Brazilian Republic, Bruneian Sultanate, Socialist Republic of Chile, Old Babylonian Empire, and
many more historical regime/dynasty-phase records). Live pending count: 635 -> 590.

### Regime-naming pattern broadened to the bare "Qualifier Place" shape — 1 September 2026

One more live catch in the same rules-tightening session: "Francoist Spain" (1939-1975) has exact
date nesting inside Spain's continuous span and matching geography, but wasn't suggested phase_of
-- `name_is_regime_of()` only recognized the explicit "X of Y" shape ("Kingdom of Hungary"), not
the far more common bare "Qualifier Place" shape most historical regime/era names actually use:
Francoist Spain, Nazi Germany, Soviet Russia, Meiji Japan, Ba'athist Iraq, Weimar Germany. Broadened
the check to any name ending in the other record's exact name at a word boundary -- the existing
finite-end gate on the "regime" side is what keeps this safe: a genuinely distinct compound-name
place that shares the same bare shape (West Virginia is not a regime of Virginia) is almost always
still open-ended, while a real regime name has almost always concluded.

Side effect on the West Virginia/Virginia regression test: since the naming pattern now genuinely
(ambiguously) matches, `no_identity_signal` no longer applies either, so the algorithm now
withholds a suggestion (`None`) instead of confidently asserting "independent" -- arguably more
honest, since there's now a real (if unresolved) naming signal rather than none at all. Updated the
test to match, plus a new case for the real Francoist Spain/Spain example. 256/256 tests pass.

Confirmed live via decisions applied during this same pass: Sharifian Empire -> phase_of Morocco
(open-ended, confirming the earlier finite-end-removal works end to end), Republic of Georgia
(1990-1992) -> phase_of Georgia the country (confirming the geography-inherit fix resolves to the
right candidate, not the U.S. state), Kingdom of Romania -> phase_of Romania, Government of Meiji
Japan -> phase_of Empire of Japan, Independent First Syrian Republic and Syrian Republic under
French Mandate -> phase_of First Syrian Republic, Lebanese Republic under French Mandate -> phase_of
French Mandate of Lebanon.

### Geography rule refined: a phase inherits its matched entity's geography when it has none of its own — 1 September 2026

Live-tested the tightening below within minutes of shipping it: "Republic of Georgia (1990-1992)"
has no `present_countries` of its own, so the newly-strict `geography_compatible` blocked its
otherwise-exact phase_of match against "Georgia" (regime_of naming pattern, finite end, dates
nesting exactly). Refined the rule: missing data on *both* sides still isn't a match, but when only
one side has none while the other does, that's not a conflict either -- a phase reasonably shares
its matched entity's location. `geography_conflict` (both sides have data, no overlap) is unchanged
and still blocks a real mismatch.

Known, discussed, and accepted tradeoff: this reopens a narrow risk of a literal name collision
(e.g. "Georgia" the country vs. "Georgia" the U.S. state) both getting suggested phase_of when the
reviewed record has no geography of its own to disambiguate with -- confirmed live on exactly that
pair. Not a silent auto-apply, though: the correct candidate still scores higher (138, high
confidence) and ranks first ahead of the wrong one (126, medium confidence). Left as-is rather than
adding cross-candidate disambiguation for what's a rare naming pattern. Two new regression tests
cover the real Georgia case and the both-sides-missing case. 255/255 tests pass.

Applied four more decisions live during this same pass: Republic of Haiti (1820-1849), State of
Thuringia (1920-1952) -- the exact record the year-range-suffix fix targeted, confirmed working end
to end -- Union of Burma (1948-1962), and United Arab Republic (1961-1971), all phase_of their
respective successor entities. Ran `pipeline.compute_prominence` afterward.

### `suggested_decision` tightened: exact date containment, real geography overlap, no finite-end requirement — 1 September 2026

Direct correction of the plain-language rules summary above (the previous session had just
written it): three deliberate tightenings, all now documented in [README.md](README.md)'s new
"Consolidation review" section rather than only here.

- **No date tolerance.** `DATE_CONTAINS_TOLERANCE_YEARS` (was 10) removed entirely --
  `date_contains`/`reverse_date_contains` now require exact boundary containment. A 1-year gap
  between two independently-estimated ancient dates (Akragas 580 BCE vs. Agrigento's record
  starting 579 BCE) now withholds the suggestion instead of guessing through it.
- **Missing geography is not a match.** `geography_compatible` previously also passed when either
  side had no `present_countries` recorded -- now it requires an actual overlap. A separate
  `geography_conflict` signal (both sides have data, no overlap) keeps the "conflicting geography"
  reason text accurate rather than firing on simply-unknown geography. This is the change with the
  largest measured effect: roughly a third of the dataset (1,487 of 4,566 records) has no
  `present_countries` data at all, and those records can no longer reach a phase_of/
  candidate_phase_of suggestion, or even a weak-token-match candidate pairing, through geography
  leniency alone -- they need a real name or Wikidata signal instead. Live pending count dropped
  700 -> 441 as a direct result.
- **No finite-end requirement.** Dropped `document.get("end")`/`other.get("end")` is-not-None from
  the phase_of/candidate_phase_of branches. The backend already approximates a missing end rather
  than refusing the decision (see the earlier open-ended-phase_of section above), so the
  suggestion shouldn't be more conservative than the backend it feeds. The one case that gate was
  protecting against -- an "X of Y"-named but still-open, broader container mistaken for a
  completed phase (Realm of New Zealand vs. New Zealand) -- is already covered by
  `regime_of_candidate`/`regime_of_reviewed`'s own finite-end requirement on the naming-pattern
  path specifically; `exact_name_match` and a direct Wikidata part-of relationship carry no such
  ambiguity.

Updated the Akragas regression test (split into a mismatched-date case that now withholds, and a
matching-date case that still suggests phase_of) and added two new ones (open-ended-both-sides
phase_of; missing-geography-data no longer counting as compatible). Fixed one pre-existing test
fixture (`tests/test_server.py`'s Ottoman Caliphate case) that relied on the geography leniency
being removed, using its real `present_countries` instead. 254/254 tests pass; zero new console
errors live.

### Two live-testing suggestion bugs fixed, a regression test suite added, and six decisions applied — 1 September 2026

Two more false suggestions caught via direct live review of the overhauled UI, both traced to gaps
in the `suggested_decision` priority chain rather than missing signal data:

**Czechoslovak Socialist Republic suggested `part_of` instead of `phase_of`.** It carries a direct
P361 claim to Czechoslovakia (added the previous session) and its dates (1948-1990) nest cleanly
inside Czechoslovakia's (1918-1992) with a finite end -- everything a `phase_of` suggestion needs
except naming evidence, since neither `exact_name_match` nor the "X of Y" `regime_of_candidate`
pattern fired for this pair. The `reviewed_part_of_candidate`/`candidate_part_of_reviewed` P361/P527
signal had been added as its own branch, checked *after* phase_of/candidate_phase_of -- so a pair
with strong date-nesting but no naming match fell straight past phase_of into the weaker part_of
default. Fixed by accepting a direct P361/P527 relationship as alternative naming evidence *inside*
the phase_of/candidate_phase_of conditions themselves (still gated on clean date-nesting and a
finite end), checked before the plain part_of/candidate_part_of fallback. A real P361 claim plus
clean nesting now wins as phase_of; a P361 claim alone (no date nesting, e.g. Realm of New
Zealand/New Zealand) still falls through to part_of/candidate_part_of as before.

**State of Thuringia (1920-1952) suggested `independent` instead of `phase_of`.** Its
`canonical_name` carries a trailing year-range disambiguator -- `"State of Thuringia (1920-1952)"`
-- which broke the `.endswith(" of thuringia")` check inside `name_is_regime_of()` even though the
name minus the parenthetical clearly reads as "State of Thuringia". Grepping the dataset for the
same pattern (`canonical_name` ending in `(YYYY-YYYY)` or `(YYYY-present)`) found six more affected
records: Kingdom of Hungary, Albertine Duchy of Saxony, Herat, Hyderabad State, Later Jin, Taifa of
Ceuta, United Arab Republic. Added `strip_year_range_suffix()` (`YEAR_RANGE_SUFFIX_RE`) and applied
it in both `name_is_regime_of()` and `consolidation_names()`, before any naming comparison runs.

**New regression test suite.** Per explicit request ("bake that into the algo and have tests on the
different examples given ... so that we can keep improving"), added
`tests/test_consolidation_suggestions.py` -- one test per real example surfaced during live review,
covering every branch of the priority chain: same_entity, phase_of (direct alias, regime-of-place,
direct P361 override, year-range-suffix naming), candidate_phase_of, part_of/candidate_part_of
(direct P361 without date nesting), independent (no signal, likely-siblings, alias-reused-different-
era), and the possible_qid_conflict/no_identity_signal null cases. 12 tests, all passing alongside
the existing 239.

**Six consolidation decisions applied live** during this same review pass: Czechoslovak Socialist
Republic, Coahuila y Tejas, and Lands of the Bohemian Crown (1348-1526) each resolved `phase_of`
their broader/successor polity; New Zealand resolved `part_of` Realm of New Zealand (subdivision);
Peru-Bolivian Confederation, Sweden, and Realm of New Zealand confirmed `independent`. A separate,
unrelated pair of live decisions on the Syrian Republic records was explicitly reverted per request
before this batch was committed.

251/251 tests pass throughout; zero console errors live beyond the pre-existing unrelated favicon
404. `/consolidation-review` "active" pending count: 706 -> 700.

### ROADMAP task 0 complete: `/explore` display half of the `detail_of` merge — 3 September 2026

The Python side (`build_explore_tree.py` excluding `detail_of` polities from their own top-level
band and attaching them as their container's `details` list) shipped 2 September 2026 (commit
`50f7ee4c`); this closes out the deferred `explore_timeline.js` display half.

**Per-lane variable height.** All three grouping-mode layout/draw function pairs
(`continentGroupedLayout`/`geoCountryGroupedLayout`/`flatLaneLayout` and their matching
`drawContinentGroupedRow`/`drawGeoCountryGroupedRow`/`drawFlatLaneRow`) assumed uniform lane height
(`laneIndex * laneHeight`). Refactored to cumulative per-lane offsets (`laneHeights`/`laneOffsets`/
`sumLaneHeights`) so a lane holding an expanded item reserves extra room without disturbing its
neighbors — items sharing one lane never overlap horizontally by construction (`packIntoLanes`), so
their panels never collide either.

**Interaction, revised twice from the original approved design during live review.** The originally
approved design (see `docs/plans/2026-09-01-detail-of-merge-design.md`'s "Deferred: `/explore`
display" section) was a small count badge plus a single row of evenly-divided, non-date-positioned
chips. Direct feedback against a live mockup (published as a Claude.ai artifact, iterated four times)
changed this twice: the badge became a full-height toggle compartment fused to the band's own left
edge ("+ N", flipping to "− N" when open, full "Show/Collapse details" wording moved to the
tooltip after a later wording-simplification pass) instead of a small floating circle —
sized off a fixed width per digit-count band so it never jitters between rows; and the detail panel
became one date-positioned line per detail (positioned/sized against the same `scale` as every other
band, so it lands under its real years) instead of evenly-divided chips, since chips carried no
positional date information at all. `drawItemBand()` now splits a container's band into the toggle
compartment plus a name segment, each with its own click target, so toggling the panel never also
opens the side detail panel and vice versa. `bandRect()` itself lost the badge-drawing code it had
briefly grown, moved out to a dedicated `drawDetailToggle()`.

**Labels gained inline dates.** Also from live feedback: Continent-mode labels
(`itemDisplayLabel()`, already the one place a "(Country)" suffix could be appended) now always
append the item's own date range in text — parent and child alike — since a date-positioned detail
line still needs its dates spelled out (it isn't drawn against a visible axis of its own the way a
top-level band is). While in there, fixed a real bug the same feedback surfaced: the "(Country)"
suffix fired even when the resolved country name just repeated the entity's own name (e.g.
"Luxembourg (Luxembourg)", "South Korea (South Korea)") — now suppressed via a case-insensitive
name/country comparison, kept whenever the two differ (e.g. "Turkey (Türkiye)", "Kingdom of the
Netherlands (Netherlands)").

**CSS:** `.hierarchy-detail-toggle`/`.hierarchy-detail-panel`/`.hierarchy-detail-chip` added to
`styles.css`, reusing existing `--paper`/`--rule`/`--ink-faint`/`#8c422d` tokens (no new colors
introduced). Verified live via chrome-devtools against the running server (rebuilt
`explore_tree.json`/`data.json` first via `python -m pipeline.rebuild_timeline`, since those are
pre-built artifacts a code change alone doesn't refresh) — deep-linking to `ba_athist_iraq` confirmed
auto-expand, multi-container expand/collapse, correct date-positioning (including a detail clipping
out of view when zoomed past its own range, same as any other band), and that clicking the toggle
vs. the name segment route to the right target. 286/286 tests pass (no Python changed this session;
re-run for safety).

### ROADMAP task "0 bis" complete: set a polity's `detail_of` from `/explore`'s own side panel — 3 September 2026

Immediately followed task 0 above. `/explore`'s side panel gained a "Set as detail of" control in a
polity's "Edit" section, mirroring `subdivision_review.js`'s existing "find another polity" parent-
picker almost verbatim (same `/api/polities/search` endpoint, same `.parent-search`/`.type-choice`/
`.type-choice-list` markup and CSS -- no new CSS needed). When `detail_of` is already set: a plain
"Currently a detail of X / Clear" line; otherwise a search box whose results are clickable buttons.
Both write through the existing generic `PATCH /api/polities/{id}/fields` endpoint (it merges rather
than replaces, so a bare `{ detail_of: ... }`/`{ detail_of: null }` body is enough -- no new backend
endpoint). Added a chain-prevention guard: `build_explore_tree.py`'s Pass 2 excludes any polity
carrying `detail_of` from its own top-level entry, so a two-level chain (A detail_of B detail_of C)
would make B vanish entirely rather than nest two deep -- picking a target that itself already has
`detail_of` set is refused with an inline message pointing at its own top-level container instead.
Verified live via chrome-devtools (State of Ecuador): set, clear, and the chain-prevention refusal
all behaved correctly; reverted the resulting `polities/state_of_ecuador.yaml` test residue (a stray
`manual_overrides` entry from set-then-clear) before committing, same discipline as the rebuild
side-effect caught and reverted for task 0 above. 286/286 tests pass (no Python changed).

### `government_form` field, and two geography-grouping bugs found via live testing — 31 August 2026

**`government_form` field added to `Polity` and `Period`.** Distinct from `entity_type`, which
only distinguishes polity/civilization/subdivision/micronation/culture/people/tribe/
archaeological_horizon with no room to record the specific kind of governed political entity --
sultanate, khanate, duchy, principality, etc. all just became `entity_type: polity`, same as
`empire`/`kingdom` already do. `GOVERNMENT_FORM_QIDS` in `pipeline/backfill_entity_types.py` maps
~35 Wikidata direct types to a controlled vocabulary (reusing the eligibility-rules research from
earlier the same day), deliberately excluding types describing recognition status or a
geographic/temporal category rather than an actual form of government. Auto-populated via a
direct P31 match only (no ancestry inference -- stays `None` rather than guessing), respecting
`manual_overrides`. No new UI: editable through `/explore`'s existing generic raw-fields side-panel
editor, confirmed no server/frontend changes were needed (same as `linked_era_id` before any
dedicated control existed for it).

**Two geography-grouping bugs found via live `/explore` testing, both fixed same day:**
- **"Unclassified" band** (Byzantine Empire, Ottoman Empire, Tang dynasty, and 1,345 of 4,651
  active polities, 29%, had no continent at all). Not missing data -- a structural limitation:
  continent was only ever derived from a polity's Wikidata P17 ("country") claim, but pre-modern
  dynasties/empires routinely have no usable P17 (Tang dynasty has none; Byzantine Empire's P17
  resolves to non-country "Roman Empire"; Ottoman Empire's P17 resolves to itself) even though
  they usually DO carry a direct Wikidata P30 (continent) claim on themselves -- confirmed live via
  the API before writing code. New `pipeline/enrich_geography.py:fill_self_continent_fallback()`
  pass fixed 367 records this way (missing-continent count: 1,345 -> 986).
- **Continent grouping too coarse** ("Byzantine should be in West Asia, not just Asia/Africa").
  Extended the fix: `resolve_from_centroid()` does point-in-polygon against a centroid, resolving
  both the ISO2 country and continent `locate_point()` already computed (only the continent half
  was being used). Filling `present_countries` from this lets
  `pipeline/derive_historical_regions.py` place the record into a real historical_region
  afterwards the normal way (Istanbul's centroid resolves to Turkey, already mapped to
  `west_asia`) -- deriving a region straight from continent instead would be exactly the coarse
  guess that module's own docstring already rules out. Found and fixed a real latent bug along the
  way: the "high-resolution" boundaries file uses a different property schema
  (`ISO3166-1-Alpha-2`, no `CONTINENT` field at all) than the matching code expects, so
  `--only-missing` has been silently non-functional since it was wired up; the new pass uses the
  low-resolution file instead, which works. Result: Byzantine Empire and Ottoman Empire now
  correctly show `primary_continent: asia`, `present_countries: [TR]`,
  `historical_regions: [west_asia]`. 31 records got `primary_continent` resolved this way, 29 got
  `present_countries` (and therefore a real region).
- Separately, also fixed the **"Central Asia" grouping** for Nogai Horde and Kazakh Khanate (and
  10 similar records): these carry a deliberate `manual_overrides: [geography]` lock leaving
  `present_countries` empty (correctly -- a shifting steppe khanate doesn't map onto one modern
  country), so they could never get a historical_region through the normal derivation. Set
  `historical_regions` by hand for all 12 based on each entity's actual history/geography, with
  `historical_region` added to `manual_overrides` so the derivation pipeline won't try to
  overwrite them.

**What's left**, tracked in ROADMAP.md: 986 records still have no continent at all (no Wikidata
QID, or a QID with neither a usable P17 chain nor a direct P30 claim nor a centroid -- needs a
different signal than anything built so far); 69 records have `present_countries` but their
country isn't yet in `pipeline/historical_regions.py`'s ~180-country starter table.

Verified throughout: build validates (4,697 entities), 239/239 tests pass, live chrome-devtools
checks show zero console errors beyond the pre-existing favicon 404.

### Heuristic/on-the-fly computation audit — 31 August 2026

Requested earlier the same day (see the `linked_era_id` field-conversion work above): a full
audit of remaining heuristic/on-the-fly computations affecting how polities, civilizations, etc.
are classified or displayed, to decide which deserve to become explicit persisted fields the same
way `linked_era_id`/`government_form` did. Dispatched a dedicated investigation across
`pipeline/build_explore_tree.py`, `pipeline/geography_overlap.py`, `pipeline/period_hierarchy.py`,
`pipeline/backfill_entity_types.py`, `pipeline/classify_period_roles.py`, `server/app.py`, and the
client-side geography-bucket dispatch in `web/explore_timeline.js`. Full results now in ROADMAP.md
item 7; summary:

- **Macro-chapter placement** (`best_chapter_for_polity`/`_best_chapter_for_range` in
  `build_explore_tree.py`) decides which of the 9 macro chapters a civ/culture/people/tribe-typed
  entity or ordinary polity lands in, by pure date overlap, whenever it has no curated route
  through `period_links.yaml`. **No override field exists at all** -- a curator disagreeing with a
  borderline pick has nothing to set, only indirect/wrong workarounds (add unrelated curation, or
  edit `start`/`end`). Structurally the closest match to what `linked_era_id` used to be before
  31 August 2026's fix. Strongest candidate for a new field.
- **Civilizations & Cultures lane membership for periods** (`_is_civilization_lane_period`) is
  true when `authority == CIVILIZATION_BACKDROP_AUTHORITY` (a real signal, but a magic string
  smuggled into a free-text field rather than a proper typed field) **or** -- the actual heuristic
  -- when "civilization"/"culture" appears as a substring of the period's `canonical_name`. No
  field exists for the real cases this fails; the only lever is renaming the record (corrupting
  the display name to fix classification) or hijacking `authority`'s free text.
- **Period -> regional-era placement** (`rank_candidates` via `build_explore_tree.py`, the same
  ranking machinery `linked_era_id` used to use) already has a real override field
  (`Period.broader_periods`) -- most periods just haven't been curated yet
  (`reports/regional_era_suggestions.jsonl` is still an open queue). Not a missing-field problem;
  a one-shot seeding pass (matching `pipeline/seed_linked_era_ids.py`'s recipe: convert today's
  best-guess picks into real `broader_periods` values) would close most of the gap without a
  schema change.
- **Entity-type P279-ancestry inference** (`classify_inherited_types` in
  `backfill_entity_types.py`) already has the right shape: writes to the real `entity_type` field,
  gated by `manual_overrides`, with an existing review queue (`/type-review`, ~2,682 pending per
  ROADMAP item 5). One real gap noted: no diff/alert when a rerun flips an *unreviewed* record's
  inferred classification out from under it between runs -- a silent-drift risk, not a missing
  correction path.
- **Automatic `timeline_role: period` conversion** (`pipeline/classify_period_roles.py`'s
  unconditional auto-convert branch, `has_entity_branch` false + an end date) writes directly to a
  real stored field and is gated by `manual_overrides`, but has no dedicated "undo" UI action the
  way the ambiguous cases (routed to `/consolidation-review`'s period/both decision) do -- lower
  priority, a UI-affordance gap rather than a structural one.
- **Everything else audited** -- `subdivision_parent_candidates`, `consolidation_review_queue`'s
  fuzzy-duplicate matching, `search_polities`'s fuzzy search ranking, geography gap-filling
  (`enrich_geography.py`/`derive_historical_regions.py`, already field+override-gated the right
  way, same pattern `linked_era_id` graduated to), and the client-side `geoBucketKey`/
  `countryLaneKey` dispatch in `web/explore_timeline.js` (pure routing on already-authoritative
  fields, not itself a guess) -- is either proposal-only behind a mandatory human-confirmation
  step before anything gets written, or doesn't decide classification at all. Fine as pure
  heuristics; no action needed.

Deliberately did not act on any of these yet -- this was an audit to inform a decision, not an
implementation pass; ROADMAP.md item 7 carries the three real candidates forward for a decision
on which (if any) to build.

**Follow-up, same day: all three built.**
- `Polity.linked_chapter_id`/`Period.linked_chapter_id` -- checked first at all three
  chapter-placement sites in `build_explore_tree.py`, ahead of both the `period_links.yaml`-
  curated path and the heuristic. `pipeline/seed_linked_chapter_ids.py` runs the real
  `build_explore_tree()` once against the unseeded dataset and reads back which chapter each
  entity landed under and whether that was curated or heuristic (rather than re-implementing that
  distinction independently, which would risk drifting from what the real build does). Seeded 835
  polities, 10 periods. Verified the seeding is visually a no-op via a live `/explore` screenshot
  before/after.
- `Period.civilization_lane` -- checked first in `_is_civilization_lane_period()`, ahead of the
  `CIVILIZATION_BACKDROP_AUTHORITY` signal and the name-substring guess.
  `pipeline/seed_civilization_lane_flags.py` seeded all 90 periods (not just the True cases -- an
  explicit False is just as much a fact worth recording).
- `Period.broader_periods` -- `pipeline/seed_broader_periods.py` converted 7 ordinary periods'
  heuristic era placement into real values (10 remain genuinely unmatched, a real data gap, not a
  curation one). Caught and reverted a real mistake from the first run:
  `periods/early_dynastic_mesopotamia.yaml` had `broader_periods: []` set *deliberately* earlier
  this session (its real relationship is "phase of Sumer", which the field can't express -- see
  the still-open "period can subdivide a civilization/polity" item below), and the seeder can't
  tell that apart from "just not curated yet" since an empty list and an absent one look the same
  to it. Documented the caution in the script for any future re-run.

All three raw-YAML seeding scripts hit the same tier-normalization gotcha (a period file omitting
`tier` reads back `None` from `yaml.safe_load`, not the schema's `"period"` default) --
`seed_linked_era_ids.py` documented it first; each later script repeats the fix on a throwaway
normalized copy, never letting it leak into what gets written back to disk. 239/239 tests pass
throughout; build validates cleanly (4,697 entities) after each step; zero console errors live on
`/explore` after each rebuild. ROADMAP item 7 (the audit itself) is now fully closed and removed
from the numbered list.

### Period/polity dataset cleanup — 30-31 August 2026

A cluster of data-quality fixes, mostly triggered by live `/explore` testing surfacing
`period<->polity` naming and duplication issues.

**Same-named period disambiguation.** 9 period records (not 8 — the original count was
stale; Poland has 3, not 2) shared an identical `canonical_name` within their group (4×
"Kingdom of Hungary", 3× "Kingdom of Poland", 2× "Kingdom of Spain"). Confirmed via live
Wikidata lookups that the English *label* is identical within each group too (only the
descriptions differ), so gave each a verified `(start-end)` date-range parenthetical —
the same convention `polities/kingdom_of_hungary_10001301.yaml` (canonical_name
"Kingdom of Hungary (1000-1301)") already established. Note: `kingdom_of_poland_q577867`
(1025-1385) and `kingdom_of_poland_q3446214` (1320-1386) overlap heavily and may describe
the same underlying continuity under two Wikidata items — a possible future consolidation
candidate, not acted on.

**Mistagged period geography.** 3 periods (`lebanese_republic_under_french_mandate_period`,
`state_of_greater_lebanon_period`, `state_of_vietnam_period` — all clearly Asian) were
tagged with 5-6 spurious continents; corrected to their real single continent/country.
Root cause traced: `server/app.py`'s consolidation-review "retire and generate a period"
endpoint (`~line 663`) copies the source polity's `geography` block verbatim into the
generated period — not a bug in that copy itself, but a carrier for `enrich_geography.py`'s
still-open Bug B (see "Honest scope warnings" below) whenever the source polity's own
geography was already poisoned before being retired. Confirms Bug B's blast radius extends
to consolidation-generated periods, not just polities.

**`european_iron_age` coverage gap.** Was a bare, unparented period. Rather than promote it
to its own `regional_era` (which would have duplicated `mediterranean_classical_era`'s
near-identical scope for the same macro chapter), nested it as `tier: period` under
`mediterranean_classical_era` instead — matching the day's other bare-period fixes (Old
Kingdom of Egypt under Egypt's era, Uruk period under Mesopotamia's).

**A real duplicate found, and a full-dataset audit it triggered.** `egyptian_old_kingdom`/
`old_kingdom_of_egypt` (and their Middle Kingdom counterparts) turned out to be a genuine
period/polity duplicate — same canonical_name, matching Wikidata QID, near-identical dates,
no distinct content. Deleted the period pair (the polities already carried the real weight).
That triggered an audit for the same shape dataset-wide (period<->polity sharing a QID): 91
candidates found. Only the Egypt pair was a true duplicate; the other 90 were two legitimate,
different mechanisms — see ONTOLOGY.md's "Polity/period duality: link, don't duplicate" for
the full pattern. All 91 were deleted in that first pass.

**Follow-up correction: 28 of those 91 were not duplicates at all.** On review, `mamluk_
sultanate_of_egypt` plus 15 "Republic of"/"Reign of" records (Cuba, Egypt, Venezuela, Sudan
×2, Congo ×2, Afghanistan, Albania, Austria, Burma, Georgia, Equatorial Guinea, Seychelles,
Amadeo I of Spain), and separately 22 "Kingdom of"/"Crown of"/"Duchy of"/"Principality of"
records (including the 9 disambiguated above, plus Burgundy, Cambodia, Italy, Navarre,
Norway, Sicily, Württemberg, Yugoslavia, Afghanistan, Castile, hispanic_monarchy — a
dangling `parent` reference surfaced along the way) — all turned out to be genuinely
distinct, narrower regime-phases within a much broader "the country/kingdom across all its
eras" umbrella polity that already existed (e.g. "Republic of Egypt" 1953-1958 vs. "Egypt"
1922-present), not duplicates of it. Restored as independent polities from their
pre-deletion git history, their now-redundant period companions removed.

House of Wessex/Plantagenet/Tudor, Norman dynasty, and Capetian dynasty needed different
handling: unlike the 28 above, these never existed as polities — they were hand-authored
period-context records from the start (earlier reference-poster gap-filling work), and each
one's own notes explicitly said their parent kingdom (kingdom_of_england/kingdom_of_france)
"already carries this span's political weight." Created as new sub-polities instead
(weight_by_era reused from the parent kingdom's own values at each century mark inside the
dynasty's span, weight_imputed: true, explicit political_parent relationship back to the
parent kingdom) rather than dropped or left as periods.

A real process failure surfaced mid-cleanup: an independent review dispatched to verify the
first restoration batch used `git stash -u`/`git stash pop` for its own clean baseline, in
the same (non-isolated) working directory this session was actively continuing to edit —
the stash round-trip landed inconsistently and resurrected 23 of the just-deleted period
files. Caught by a full audit of every record touched (not a spot-check), re-fixed, and
re-verified clean.

**Smaller fixes along the way:**
- `aztec_triple_alliance_period` deleted — a genuine duplicate of the already-weight-bearing
  `aztec_empire` polity (which lists "Triple Alliance" as an alias and already carries real
  `weight_by_era` data), unlike the 28 above.
- `dacia` renamed "Dacian Kingdom", `entity_type` changed `civilization` -> `polity` — it had
  a real, specific unified political actor (documented kings), unlike the Civilizations &
  Cultures lane's other residents.
- `akkadian_empire` elevated `entity_type: polity` -> `civilization`, and `uruk_period`
  renamed "Uruk period" -> "Uruk culture" (a real archaeological synonym) to route it into
  the lane — both per direct editorial decision, after a contrary technical opinion was
  raised and heard (this project's `civilization` convention otherwise means "no single
  political actor," which doesn't describe either record) and the call stood regardless.
- `sumer` promoted to `visibility_override: global` — `entity_type: culture` already routed
  it toward the Civilizations & Cultures lane, but `visibility_tier: detailed` excluded it
  from `/explore` entirely (the same gate the ordinary Polities row uses); its automated
  score (33.0) clearly undersold its importance.
- The Civilizations & Cultures lane gained a second, more reliable routing signal
  (`CIVILIZATION_BACKDROP_AUTHORITY`, checking a period's `authority` field directly) after
  discovering `ancient_egypt_period`/`babylonia_period`/`chinese_empire_period` had silently
  fallen out of the lane once their source polities were deleted in the 91-record audit above.
- `early_dynastic_mesopotamia` given `broader_periods: [mesopotamian_early_states_era]` (was
  bare) for tree placement — its separate `context`-relation link to the `sumer` polity
  (via `period_links.yaml`) is untouched and is the more semantically correct relationship,
  but the schema has no mechanism yet to nest a period under a *polity/civilization* rather
  than an *era* for tree-placement purposes; see ROADMAP.md's "Ideas" section.
- `neolithic_era` renamed "Neolithic & Archaic" and extended to cover the Americas: the
  Mesoamerican and Andean "Archaic" regional eras describe the same underlying
  agricultural-transition process as the Old World's Neolithic siblings already nested here,
  just under the Americanist archaeological term ("Archaic," not "Neolithic" — a real
  terminology difference, not just a regional relabeling, which is why the umbrella kept
  both names rather than stretching "Neolithic" to cover it). Demoted both to `tier: period`
  underneath it; no date-range extension was actually needed, both were already within the
  existing -10,000 to -1,700 span — only `continents` needed the addition.

Verified throughout: `build.py` clean (no dangling `parent`/`successors`/`relationships`/
`period_links.yaml` references) after every step, full test suite green (238/238 by the end).

### Current measurable state

*(This block had gone stale — some figures below hadn't been refreshed in a long time, e.g. the
test count was still off an old 137. Re-measured live 31 August 2026 via the running server's
`/api/review-dashboard`/`/api/reviews` endpoints, `git`, and direct dataset counts; treat these as
current until the next re-measurement, and re-measure rather than trust old copies of these
numbers elsewhere in this file or in ROADMAP.md.)*

- **4,697** canonical polities (4,663 + the 34 Seshat unmatched drafts imported this pass, see
  below).
- **242** automated tests passing; `build.py` validates **5** curated transitions, **90** periods,
  and **17** period links (down sharply from 102/97 as this session's period→polity conversions —
  Han dynasty, Tibet, the Commonwealth-realm batch, 29 modern-era `phase_of` companions, etc. —
  each removed both the `periods/*.yaml` record and its `period_links.yaml` entry).
- Seshat reconciliation: the reviewable "review" sub-queue is **fully cleared** (0 pending,
  confirmed live via `/api/reviews` returning `total: 0`); `reports/seshat_review_decisions.jsonl`
  currently holds **258** decisions (109 accept / 149 reject). The **34 unmatched** drafts
  (`reports/seshat_unmatched_drafts.yaml`) are no longer inert — `pipeline/
  import_seshat_unmatched_drafts.py` (new, idempotent) wrote each as a minimal draft
  `polities/*.yaml` and queued an honest `/type-review` entry for each (proposed_type
  `archaeological_horizon`, confidence `low`, reason states plainly there's no automated Wikidata
  evidence behind the proposal since these records have no Wikidata item at all). Closes the
  ROADMAP item that used to sit here.
- Entity consolidation: **845 pending** (confirmed via `/api/review-dashboard`: 60 high-confidence,
  718 medium, 98 flagged as polity→period candidates) — down substantially from the 4,336 this
  file and ROADMAP.md had both been citing from a much older, unrefreshed snapshot.
- Wikidata type-eligibility: **661** still flagged `review` across canonical `polities/*.yaml`,
  down from 1,948 after the 31 August 2026 rules-table expansion (see above) closed a large
  not-actually-ambiguous gap.
- Entity-type classification (polity/civilization/culture/people/tribe/archaeological_horizon):
  **2,682 pending** (confirmed live), down from 3,098 after the same rules-table expansion.
- Subdivision-parent classification: **2 pending** (confirmed live via `/api/review-dashboard`).
- Period-role (polity→period reclassification) queue: **103** ever seeded into
  `reports/period_role_review.jsonl` (94 from the original Wikidata-ancestry signal plus 23 from
  a new entity_type-based signal added 31 August 2026, minus a few already resolved), **98 still
  open** per the live consolidation-queue breakdown.
- Also recomputed `prominence_score`/`prominence_components` dataset-wide twice this stretch
  (`pipeline/compute_prominence.py` hadn't run since before this session's period→polity
  conversions, then again after the type-eligibility/entity-type rules expansion shifted
  relationship counts for many newly-typed records) — no other fields touched either time.
- Geography and editorial-coverage figures from the July snapshot have not been re-measured this
  pass; re-run `pipeline/enrich_geography.py`'s coverage report before citing them again.

---

## Implementation steps

### Phase 0 — Foundations

Setup, schema, smoke test. Goal: a validated YAML file you can build the rest of the pipeline on.

1. **Repo & environment.** Create `histomap/`, `git init`, add `.gitignore` for `sources/`, `__pycache__/`, `.venv/`, `*.parquet`, `*.duckdb`, `data.json`. Python 3.12 virtualenv. Pin `requirements.txt`:
   ```
   pandas>=2.2  pydantic>=2.7  SPARQLWrapper>=2.0  rapidfuzz>=3.9
   pyyaml>=6.0  xarray>=2024.5  netCDF4  openpyxl  unidecode
   ```
   Add a `justfile` (or Makefile) with `extract`, `reconcile`, `compute-weights`, `build`, `validate`, `serve` targets so the pipeline is one command end-to-end.

2. **Schema.** Write `schema.py` with the Pydantic model above. Enums for `*_confidence` (`high|medium|low|legendary`) and `culture_group`. Validators:
   - `end > start` (allow `end = None` for still-extant polities).
   - `weight_by_era` keys are integers (negative = BCE), values in `[1, 10]`.
   - `external_ids.wikidata` matches `^Q\d+$`.
   - `id` is `snake_case`, unique across the dataset.
   - `start` / `end` within `[-10000, 2100]`.
   Add `just validate` that loads every file in `polities/` and fails on any error; wire it into a pre-commit hook so bad YAML never lands.

3. **Smoke test.** Hand-write `polities/rome_republic.yaml` with every field populated and realistic values. Run validation. Then write a 20-line `build.py` stub that loads the directory and emits `data.json`. Confirm round-trip works.

**Done when:** `just validate && just build` succeeds on a one-file dataset and produces a JSON blob you can `jq` into.

### Phase 1 — Wikidata backbone

Get ~3,000 polities into draft YAML and render them. Quality is bad on purpose — the point is end-to-end flow before adding quality.

4. **SPARQL extraction.** `pipeline/extract_wikidata.py` runs one query per class, using `wdt:P31/wdt:P279*` to catch subclasses. Starter set of classes: state (Q7275), empire (Q48349), kingdom (Q417175), civilization (Q3024240), plus former country (verify the current QID against Wikidata before locking it in). For each entity, pull:
   - labels (`en`, `fr`, native), aliases
   - English Wikipedia article sitelink
   - `P571` inception, `P576` dissolution (with qualifiers — Wikidata often has multiple inception dates)
   - `P2046` area, `P1082` population (capture point-in-time qualifier where present)
   - `P17` country, coordinates, `P18` image
   - all classes the entity matched (for debugging coverage)
   Paginate with `LIMIT 5000 OFFSET …`; the WDQS times out on the unioned query. Cache responses to `sources/wikidata_raw/<class>.json` so reruns are free and the upstream version is auditable. Final output: `sources/wikidata.parquet` indexed by QID.

5. **Dedup.** Group by QID. When an entity matches multiple classes (Roman Empire is both `empire` and `state`), keep one row and stash the class list in a `wd_classes` column. Drop entries with no inception year — that filters out modern administrative junk and stub items. Log dropped counts per class.

5a. **Direct-type eligibility filter.** The broad `wdt:P31/wdt:P279*` class traversal is useful for discovery but leaks cities, administrative regions, archaeological sites, fictional states, and organizations into the polity set. Fetch and retain every entity's direct `P31` (`instance of`) values, then classify records before YAML generation:
   - Exclude cities, towns, settlements, archaeological sites, buildings/fortresses, organizations, fictional entities, and modern first-/second-level administrative subdivisions.
   - Do not infer eligibility from the English label: names such as “Mexico” may denote a valid sovereign country, while “Athens” may refer to the modern city rather than the historical polity.
5b. **Typed historical entities.** Canonical records now distinguish `polity`, `civilization`,
   `culture`, `people`, `tribe`, and `archaeological_horizon`. Classification first honors
   preferred-rank Wikidata `P31` statements, then consults a cached, rank-aware `P279` subclass
   hierarchy when a direct class is more specific than the controlled vocabulary. Direct matches
   are high confidence; inherited paths remain reviewable and retain their source QIDs and
   explanation. A specific contextual branch may supersede a generic polity branch, preventing
   classes such as `historical country` from hiding `civilization`. Conflicting and unmapped cases go to
   `reports/entity_type_review.jsonl`. Political parent/successor fields are restricted to polity
   endpoints, while evidence-bearing typed relationships represent political containment and
   succession, cultural sequence/components, associated peoples, archaeological sequence, and
   civilization membership. Prominence, demographic weight, filters, timeline styling, and detail
   text are type-aware; cultures, peoples, tribes, and archaeological horizons render as context
   bands rather than population-weighted political bands. `entity_type` manual overrides remain
   locked against later automated backfills. A dedicated `/type-review` workspace presents the
   confidence-prioritized classification queue with source links, definitions, keyboard decisions,
   and immediate locked saves; `/review` remains exclusively for Seshat-to-Histomap identity
   reconciliation so the two editorial questions stay distinct.
   - Permit genuine sovereign city-states and historical poleis only when a direct type or authoritative source supports political independence. Prefer a distinct historical entity such as Classical Athens over reusing the modern-city item.
   - Put ambiguous mixed-type records into `reports/type_review_queue.jsonl` with their direct types, dates, and matched broad classes; never silently discard them.
   - Maintain versioned allow/deny type lists in `pipeline/wikidata_types.toml`. Manual per-QID overrides handle exceptional entities without weakening the global rules.

   Emit type-filter counts and representative examples for each decision (`accepted`, `excluded`, `review`). Regression spot checks must include Mexico (`Q96`, accepted as a country), Mexico City (`Q1489`, excluded), modern Athens (`Q1524`, excluded), and an accepted reviewed historical polis/city-state.

6. **Auto-convert to YAML.** `pipeline/wd_to_yaml.py` maps each eligible Wikidata row to one draft file:
   - `id = slugify(label_en)`, suffix with last 4 of QID on collision.
   - `start = year(P571)`, `start_confidence: low`. Same for `end`.
   - `weight_by_era: {start: 5}` placeholder, `weight_imputed: true`.
   - `external_ids.wikidata = QID`. Everything else: empty.
   Commit the generated files as one bulk commit titled `wd: initial import` so future hand-edits show clearly in `git log`.

7. **First renderer (completed and superseded).** The initial coverage renderer evolved into a
   horizontal vanilla-SVG timeline with weighted labelled bands, geographic swimlanes, confidence,
   details, transitions, filters, and zoom. It still serves the original purpose of making coverage
   gaps and modern-data density visible.

7a. **Prominence and visibility tiers.** Keep the complete canonical dataset, but prevent obscure entities and administrative subdivisions from overwhelming the default chart. `pipeline/compute_prominence.py` now computes an auditable score from six independently capped components: Wikidata reach (30), authoritative-source coverage (20), historical-weight evidence (20), relationship/transition centrality (15), longevity (8), and editorial work (7). Low-confidence types and dates are explicit penalties. Wikidata aggregate/sequence records are penalized, and present-country geography is deliberately not treated as political subordination. Every component is stored in `prominence_components` alongside the total score.
   - `global`: a balanced shortlist of major polities and civilizations suitable for a world-history overview.
   - `regional`: important regional polities, visible when the reader asks for more detail.
   - `detailed`: the full research dataset, including minor and disputed entities.

   Assignment is deterministic but not one global threshold: an absolute shortlist is combined with quotas for every continent/historical-era stratum, preventing well-documented regions and eras from crowding out others. Unreviewed or low-type-confidence records remain detailed; cultures, peoples, tribes, and archaeological horizons are contextual bands and cannot be promoted automatically to the global tier. Manual overrides still win, and no automated score deletes canonical data.
   A versioned `visibility_override` may promote or demote exceptional records when the automated
   score clearly conflicts with their editorial world-history importance. Prominence recomputation
   preserves this override rather than silently reverting the decision.

7b. **Political relationships and display groups.** `pipeline/enrich_relationships.py` extracts Wikidata relationship candidates using `P361` (part of), reciprocal `P527` (has part), `P17` (country), `P155`/`P156` (follows/followed by), and `P1365`/`P1366` (replaces/replaced by). Keep three concepts separate:
   - `parent`: accepted political containment, used when one polity was genuinely subordinate to or contained by another.
   - `successors`: chronological continuity, splits, and replacements.
   - `group`: an editorial display umbrella such as Roman polities, Chinese dynasties, or the British Empire; groups may collapse into one band in the global view and expand in regional/detail views.

   Never treat `P17` or `P131` as automatic political ancestry: for historical entities they often describe present-day location or modern administration. Score candidates using reciprocal statements, date compatibility, and source agreement. Auto-accept only strong reciprocal matches; retain the Wikidata property, confidence, and evidence for weaker candidates and send them to the Phase 4 review queue. Relationship cycles and impossible date ordering fail validation.

7c. **Geographic enrichment.** `pipeline/enrich_geography.py` assigns at least a continent and one or more present-day countries to every polity where evidence permits. The canonical geography block stores `continents`, ISO 3166-1 alpha-2 `present_countries`, an optional centroid, and `confidence`.
   - Prefer historical polygons from Cliopatria/Seshat and intersect them with Natural Earth modern-country polygons; this supports polities spanning several current countries.
   - Until polygons are available, use Wikidata coordinates (`P625`) and reverse-map the point into a modern country and continent.
   - Treat Wikidata `P17` and `P131` only as fallback candidates, because their meaning is inconsistent for extinct polities.
   - Keep multi-continent and multi-country results rather than forcing one location. Preserve the evidence and mark centroid-only or inferred assignments as low/medium confidence.
   - Preserve a single `primary_continent` for display placement, preferably from the centroid's
     Natural Earth country intersection. The full continent list remains available for filtering;
     multi-continent records are not duplicated into a separate swimlane.

   Emit a coverage report by century and visibility tier. Missing geography remains explicit rather than being guessed. The web view uses these fields for continent/country filters and, later, a linked map.

7d. **Entity consolidation.** The Wikidata `wdt:P31/wdt:P279*` traversal and Seshat-only draft
   materialization both leave near-duplicates in the canonical set: the same polity imported under two
   labels, or a short-lived phase of a larger polity that Wikidata treats as its own item. The
   consolidation dashboard (`/consolidation-review`) walks every active, non-excluded record with no
   `consolidation_status` yet and proposes up to five candidates, scored on shared Wikidata QID, exact
   name/alias match, shared identity tokens (name minus stopwords such as "empire," "kingdom,"
   "dynasty" and their French equivalents), present-country overlap, and date containment/overlap. A
   pairing is only proposed when it shares a QID or exact name, or clears a combined date, geography,
   and name-similarity bar, and only against records of equal or higher prominence, so a low-prominence
   duplicate always points at its more prominent sibling rather than the reverse.

   Reviewers resolve each record as independent; the same entity as the candidate (folds its name into
   the survivor's aliases and merges its sources); a phase or constituent part of the candidate
   (retires the entity and regenerates it as a `periods/*.yaml` context record linked back to the
   candidate via a `phase_of` period link); or discarded entirely as out of Histomap's scope. Decisions
   are durable (`consolidation_status`, `manual_overrides`) and, like Seshat review, must not be
   overwritten by pipeline reruns. This is the largest live review queue: 333 of 4,669 active records
   triaged, 4,336 still untouched.

7e. **Subdivision classification.** Entities marked `entity_type: subdivision` in the entity-type
   review queue (administrative regions rather than sovereign polities) need a governing polity rather
   than a `parent`/`successor` chain. The subdivision dashboard (`/subdivision-review`) proposes parent
   polities by walking Wikidata containment statements (`P131` administrative unit, `P361` part of,
   `P17` country) up to three hops with depth-decayed scoring, adding present-country geography as a
   fallback signal and any already-set canonical `parent` as a strong prior; only targets whose own
   `entity_type` is `polity` are proposed. Confirming a parent sets `subdivision_parent_status:
   confirmed` and records an `administrative_part_of` relationship, keeping subdivisions out of the
   main political parent/successor graph while still anchoring them geographically. New and barely
   started: 4 records reviewed.

**Done when:** the streamgraph renders all imported polities at the selected visibility tier; strong parent/successor relationships can be grouped or expanded; the geography report shows continent and present-country coverage, with unknowns visible for Phase 2 to improve; and the consolidation and subdivision queues are empty enough that duplicate or misclassified records no longer clutter the default view.

### Phase 2 — Authoritative overlay

Reconcile Seshat and the territorial atlas data into the Wikidata draft set. After this, the pre-1500 picture should be markedly less embarrassing.

8. **Download sources.** Seshat: bulk export from the public databank (CSV per equinox dataset). Cliopatria / chronological atlas data: GeoJSON polygons + metadata. Drop everything into `sources/` (gitignored). Record exact dataset version and download date in `sources/MANIFEST.md` — this is the only thing that makes the pipeline reproducible later.

9. **Normalize Seshat.** `pipeline/extract_seshat.py` produces a flat table: `(polity_id, start_year, end_year, area_km², population, social_complexity_index, nga, polity_alt_names)`. Seshat encodes dates as text (`"c. 550 BCE"`, `"early 4th century CE"`); write an explicit date parser with rules for `c.`, BCE/CE, century language, and date ranges. Ambiguous parses: keep the row, set `start_confidence: medium` and stash the raw string in `notes`.

10. **Reconcile.** `pipeline/reconcile.py`:
    - **Name normalization:** lowercase, strip diacritics (`unidecode`), drop `{Empire, Kingdom, Dynasty, Caliphate, the, of}`, transliterate non-Latin.
    - **Name score:** `rapidfuzz.WRatio` on normalized names, also matching against Wikidata aliases (not just primary label).
    - **Date overlap:** Jaccard of the (start, end) year intervals.
    - **Auto-accept** when `name_score ≥ 90` AND `date_overlap ≥ 0.5`. Upgrade both `*_confidence` to `high`, pull in Seshat territory + complexity, append Seshat ID to `external_ids`.
    - **Soft match** when `70 ≤ name_score < 90` OR `date_overlap < 0.5`: emit to `reports/review_queue.jsonl` with both source rows for Phase 4 LLM triage.
    - **Seshat-only:** entries with no Wikidata candidate become new draft YAMLs (`notes: "Seshat-only"`, no Wikidata external_id).
    - Emit `reports/reconcile_summary.md` with counts per century: auto-accepted / queued / unmatched. This is the dashboard for whether the phase worked.

11. **Re-render.** Same streamgraph as Phase 1, now colored by `start_confidence` (high = solid, low = hatched/translucent). Spot-check 10 well-known polities spanning eras — Akkad, Achaemenid, Han, Sasanian, Abbasid, Song, Mongol, Ottoman, Mughal, Qing — by clicking through to verify dates and territory. If those look right, the matching logic is correct enough to continue.
    The reproducible baseline lives in `pipeline/spotcheck.py` and writes `reports/phase2_spotcheck.md`; incomplete source and present-country coverage remains visible as warnings.

**Done when:** the reconcile report shows ≥ 60% of Seshat polities auto-matched, the confidence overlay shows pre-1500 CE noticeably less murky than after Phase 1, and the 10 spot-checks pass without obvious wrongness.

### Phase 3 — Weight computation

Compute `weight_by_era` from territory, population, and complexity. The output is what makes the streamgraph *honest* about scale — Han Dynasty should dwarf Lan Xang.

12. Download Maddison Project (`mpd2023_web.xlsx`, ~5 MB) and the HYDE 3.5 baseline
population-count NetCDF (~640 MB compressed). Add both to `sources/MANIFEST.md` with version.
HYDE downloads are slow and rate-limited — do it once and cache aggressively.

13. `pipeline/extract_maddison.py`: long-format table `(country, year, population, gdp_per_capita)`. Country codes are modern ISO — map to our polity IDs only for 1500+ entities; pre-modern populations fall back to HYDE.
    The extractor targets the official MPD 2023 workbook, detects its data sheet/header, converts
    population from thousands to persons, and emits `sources/maddison.parquet` plus a coverage report.
    `pipeline/map_maddison.py` initially joins only accepted, extant post-1500 polities directly
    typed by Wikidata as countries/sovereign states and having exactly one present-day country;
    historical and multi-country entities wait for polygon-based allocation.

14. `pipeline/extract_hyde.py`: load with `xarray`, aggregate gridded population to polity territory. **Catch:** we only have polygons for the Seshat-covered ~600 polities. For everyone else, fall back to the polity's NGA centroid + a regional radius, or use the modern successor's footprint as a crude proxy. Mark these with `weight_imputed: true`. Persist `sources/pop_by_polity.parquet` keyed by `(polity_id, year)`.
    The first implementation reads population-count NetCDF grids and emits explicitly imputed
    centroid-radius estimates; polygon aggregation remains the next accuracy upgrade.

15. `pipeline/compute_weights.py`:
    ```
    raw(polity, year) =
        0.4 · log10(area_km² + 1)
      + 0.4 · log10(population + 1)
      + 0.2 · normalized_complexity
    weight(polity, year) = clip(10 · raw / p95(raw_in_century), 1, 10)
    ```
    Persist sparse `weight_by_era` at 50-year resolution where data exists; linear interpolation fills the gaps at render time. Any polity with one or more missing components gets `weight_imputed: true`.
    The initial implementation prefers Maddison for mapped modern states, otherwise uses HYDE,
    interpolates Seshat area/complexity, and median-imputes missing components by century. Extant
    sovereign microstates absent from Maddison retain neutral placeholders rather than misleading
    centroid-radius totals. All current computed records remain marked imputed until polygon coverage
    replaces the HYDE radius fallback.

16. **Tunable.** All coefficients, the per-century normalization, and the imputation fallbacks live in `pipeline/weights.toml`. Re-tuning is one file edit + `just compute-weights` — the canonical YAMLs are rewritten in-place, the diff lands in git for review.

**Done when:** spot-checked band widths reflect actual scale (Han ≈ Roman ≈ heavy, one-city kingdoms thin), and a sensible perturbation to `weights.toml` (e.g., raise the area coefficient) shifts the streamgraph the way you'd expect.

### Phase 4 — LLM review queue
15. Estimate the workload/price of doing this step entirely. We don't want to have something too costly
15 bis. Write `pipeline/llm_propose.py`: for each candidate polity, send the merged source rows to the ChatGPT API, get back a structured proposal with conflict notes and child/adult reading-level text.
16. Write `pipeline/review_cli.py`: terminal UI that walks proposals, shows diff vs. existing YAML, accepts with Enter, edits in `$EDITOR`, skips with `s`.
    The first review pass handles Seshat reconciliation candidates with numbered accept, reject,
    defer, and resume support. Decisions are tracked in JSONL and reapplied idempotently by the
    reconciler; structured proposal diffs and editor integration remain later enhancements.
    Review order uses an auditable editorial-value score: 30% Seshat source importance (population,
    area, complexity, and duration), 25% canonical prominence, 20% match quality, 10% ambiguity
    requiring human judgment, 10% visibility tier, and 5% missing Seshat coverage. This puts
    consequential global-history decisions ahead of obscure or weak matches without letting a bad
    proposal inherit importance merely because its suggested target is famous.
    The web review card labels the Seshat record separately from canonical Histomap candidates,
    exposes source/canonical dates and external links, and explains both the queue-priority score and
    candidate match components. Match scores are ranking aids, not probabilities.
17. Run the review. Budget: 5s per polity × ~500 polities = ~40 minutes. Expect to spend longer on disputed dates.

### Phase 5 — Manual editorial pass
18. Create `transitions.yaml` for non-trivial splits/merges (Roman fragmentation, Mongol partitions, decolonization). ~50 entries total.
    Transition records now have validated split/merge/succession shapes, canonical polity references,
    source URLs, a separate generated web payload, and restrained chart connectors. The Treaty of
    Verdun, the Roman division, the Austro-Hungarian Compromise, the German Revolution, and the
    partition of British India form the initial curated set; remaining transitions stay manual.
    A dashed-line legend identifies transitions; connectors are mouse/keyboard selectable and open a
    source-linked drawer with the event date, editorial note, and navigable source/target entities.
19. Draw or source SVG icons for the top ~50 polities into `icons/`.
20. Tighten short-child text for the top ~50; the LLM's first pass is usable but uneven.

### Phase 6 — Web view
21. Write `build.py`: YAML files → single `data.json` (compact, indexed by era).
22. Build the streamgraph in `web/`:
    - Horizontal time axis with one compact row per polity; band thickness encodes weight, labels
      are left-aligned inside bands, and splits/merges come from `transitions.yaml`.
    - Reading-level toggle (child / adult).
    - Historical-grouping, continent, present-country, and visibility-tier filters; era zoom and hover cards.
    - Collapsible display groups derived from reviewed political relationships.
    - Linked geographic map once historical polygon coverage is sufficient.
    - Confidence shown as opacity or hatching.
    The current timeline implements the horizontal axis, compact weighted bands, confidence styling,
    collapsible geographic swimlanes and legend, visibility/continent/country/historical-grouping filters, and
    Adult/Child drawer text with fallbacks. Reviewed relationship groups, transitions, and the linked
    map remain later increments.
    An entity finder searches canonical names, English aliases, and stable IDs; selected lower-tier
    records are temporarily surfaced in context without switching the entire chart to Full dataset.
    Era presets cover major historical periods, with exact custom year fields and an entity-lifetime
    zoom action in the detail drawer.
23. Serve the timeline and editorial workspace from one FastAPI application. Local mode binds to
    `127.0.0.1`; any public deployment must authenticate write actions. Static assets remain
    independently deployable if a read-only public mirror is wanted later.

### Phase 7 — Print poster
24. Write `print/render.py`: master SVG at A1/A0 dimensions, vector text, embedded legend and methodology footer.
25. Export PDF via headless Chromium or `paged.js`.
26. Print at local shop. Frame.

### Phase 8 — Grow with the kid
- Fill `long_en` text for top polities over time. Doing this together is part of the project.
- Add reading levels 2 and 3 (ages 9–12 / teen) as additional text fields.
- Add regional zoom views, language toggles, family-history band at the bottom, map integration if interest holds.
- **Historical-period context pilot:** model periods separately from polities so chronology never
  implies political parenthood. Start with Egypt/Mesopotamia, Japan, Mesoamerica, and European
  prehistory. Each period records its kind (`historical`, `protohistorical`, `prehistorical`),
  temporal bounds, geographic scope, broader/following periods, source authority, and optional
  Wikidata, DBpedia, and PeriodO identifiers. Polity-to-period links are many-to-many and carry an
  evidence level (`explicit`, `derived`, or `suggested`); date overlap alone is never sufficient.
  Validate and publish `periods.json` and `period_links.json` first. A background-band/filter UI is
  deferred until the four-region pilot demonstrates useful coverage without misleading global
  periodization.
  The pilot is implemented end to end: the original 14 sourced authority records and 10
  evidence-bearing links are schema-validated, published by the build and unified server, and
  summarized in `reports/period_pilot_summary.md`. The timeline renders a separately styled
  period-context layer within the relevant continental lanes, with type/record controls,
  source-rich period details, period navigation, and reciprocal evidence labels on linked entity
  details.

  Two more mechanisms now generate `periods/*.yaml` records beyond that hand-curated set: a
  `phase_of`/`part_of` consolidation decision (item 7d, Entity consolidation, above) retires the
  reviewed entity and regenerates it as a period linked back to its parent polity, and a
  `timeline_role` decision of `period` or `both` (the `/period-review` queue, backed by
  `reports/period_role_review.jsonl`) marks a Wikidata item whose canonical entity band should
  also, or instead, render as a period-context band — `both` keeps the political entity and adds a
  `part_of_periodization` link back to itself. Together these have grown the period set from 14 to
  102 records, with 94 more awaiting a role decision. Expanding and curating global authority
  coverage, and reconciling the growing auto-generated set against the original hand-curated
  periodization, remain ongoing dataset work, not a UI blocker.
- **Nice-to-have relationship navigation:** make parent, children, predecessors, and successors clickable in the detail card; add breadcrumbs, related-band highlighting, and a small tree centered on the selected polity. Later, allow scrolling to a related band and expanding/collapsing descendants or reviewed display groups. This is intentionally deferred until relationship review has improved the underlying links.
  The first increment now exposes all four relationship directions, highlights the selected entity's
  visible neighborhood, and lets related links surface and scroll to lower-tier records. Breadcrumbs,
  a compact tree, and group expansion remain deferred.
- **Nice-to-have geographic/relationship layout:** replace alphabetical band order with a stable hierarchy of continent → present-day country → reviewed relationship/display group. Within a geographic block, keep parents, children, predecessors, and successors adjacent where possible, then use prominence and chronology as deterministic tie-breakers. Multi-country or multi-continent polities should appear once in a clearly defined primary block, with visual links or cross-references from their other regions rather than duplicated bands. Unknown geography gets an explicit final block. Preserve an optional alphabetical order for lookup and debugging. This layout is deferred until geography coverage and relationship review are reliable enough that automated grouping will not mislead readers.

---

## Honest scope warnings

- **Wikidata quality drops off a cliff before ~1000 CE.** Automated pipeline gives ~60% accuracy for ancient history, ~95% for modern. The visual tolerates this; don't expect Bronze Age polities to be as crisp as the 19th century.
- **Seshat is sparse.** It covers ~35 Natural Geographic Areas, not the whole world. Regions outside Seshat coverage rely on Wikidata only and stay at `confidence: low`.
- **Pre-3000 BCE is mostly archaeological cultures, not polities.** Represent them as broad bands ("Bronze Age Mesopotamia"), not as crisp entities.
- **Source disagreements are normal.** Keep them in the `notes` field rather than pretending they don't exist. The `*_confidence` fields are the right place to surface this in the viz.
- **`geography.continents` multi-continent bug — turned out to be two separate bugs.** First
  noticed as "`antarctica` incorrectly present alongside genuine continent(s)" during the
  period-ontology plan's Task 4.
  - **Bug A — fixed 2026-08-30, 103 polities repaired.** `pipeline/enrich_geography.py`
    resolved each polity's Wikidata P17 ("country") claim to derive geography, unioning in the
    target's continent claims *unconditionally* — even when the target had no valid ISO2 code
    and therefore wasn't a real country. `alawite_territory`'s P17 claim resolved to Q179023,
    "French colonial empire," which correctly has no ISO2 code but (on its own terms) has
    Wikidata continent claims for everywhere France ever held colonial territory — all 6
    non-Antarctic continents got unioned in, with `present_countries: []` since no valid
    country ever contributed. Fixed by gating the continent union behind the same
    ISO2-validity check that already gated the country-code union. Repair (a fresh
    `--offline` run after the fix) was independently re-derived twice against the
    `fe20b481`-baseline snapshot before being trusted — confirmed to correctly and completely
    fix exactly 103 polities, every one narrower-or-equal, zero `manual_overrides`-locked
    files touched. Two genuine Antarctic micronations (`westarctica`,
    `grand_duchy_of_flandrensis`) were unrelated and correctly tagged throughout.
  - **Bug B — found 2026-08-30, root cause understood, fix not yet attempted.** A different
    ~60 polities (`france`, `caliphate_of_cordoba`, `duchy_of_normandy`, and others) are
    unaffected by Bug A's fix because their P17 resolves to one or more *real*, valid-ISO2
    countries — `caliphate_of_cordoba` has 9 P17 targets (Spain, Portugal, Morocco, Algeria,
    Gibraltar, Andorra, France, Italy, Switzerland — implausibly broad for a state centered on
    Iberia, itself a Wikidata data-quality issue upstream of this pipeline). Since every target
    passes the ISO2 gate, Bug A's fix has no effect. Compounding it: some targets are modern
    states whose *own* Wikidata continent claims are legitimately multi-continental because of
    real overseas territories — `france` (Q142) genuinely has Wikidata P30 claims for Africa,
    Antarctica, Europe, and Oceania (French Guiana, Réunion, French Polynesia, French Southern
    and Antarctic Lands), which is accurate for modern France but not useful for deriving a
    *historical* polity's extent. A real fix likely means using each P17 target's *primary*
    continent rather than its full continent set — not implemented, needs its own careful pass
    (this whole area has proven fragile — see below).
  - Separately, 3 `periods/*.yaml` records (Lebanon x2, Vietnam) show the same multi-continent
    symptom but carry `authority: "Histomap editorial consolidation"`, not either bug's
    raw-import path — `enrich_geography.py` only touches `polities/*.yaml`, so their root cause
    is untraced and still open; see the `/explore` status section above.
  - **Process note, for whoever picks up Bug B:** the first attempt at Bug A's repair caused a
    real data-loss incident (an overly broad "revert collateral changes" step destroyed 7
    files' worth of unrelated uncommitted edits — recovered where the exact diff had been seen
    earlier in-session, unrecoverable for the rest) and a second attempt left the branch in a
    confusing half-finished state (a stray `git reset` silently dropped an unrelated already-committed
    commit, recovered from `reflog`). The classification logic that separates "real geography fix"
    from "collateral noise from the script's unrelated `historical_regions`-dropping write-path bug"
    is the exact step that went wrong both times — write it carefully, diff every changed file
    against a real pre-change baseline (not against a partially-repaired working tree), and verify
    exhaustively (subset-only continents, `historical_regions` preserved, `manual_overrides`
    respected, zero overlap with anything already known-uncommitted-for-other-reasons) before
    trusting any bulk classification of "safe to discard."
