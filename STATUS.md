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
| 1 — Wikidata backbone | **Partial** | Extraction, caching, direct-type rules, YAML import, prominence tiers, relationships, geography, entity-consolidation dashboard, subdivision-parent classification | Resolve 1,948 type-eligibility review flags and 3,222 pending entity-type classifications; work down the consolidation queue (333/4,669 triaged); accept reviewed display groups; improve relationship review |
| 2 — Seshat overlay | **Nearly done** | Equinox extraction, fuzzy/date/geography reconciliation, review report, 10/10 spot checks, 223 more review decisions applied | Only 35 review + 34 unmatched records left (down from 227 + 64); auto-match rate holds at 81/373 (21.7%), still short of the 60% target |
| 3 — Weights | **Initial implementation** | Maddison/HYDE extraction, mapping, tunable coefficients, sparse era weights | Historical polygon allocation and measured area/complexity; the large majority of records are still imputed |
| 4 — Review workflow | **Partial, in active use** | Prioritized web review, provenance, score explanations, source links, saved decisions, pipeline actions, plus new consolidation/subdivision/period-role review UIs | Complete review pass across all four queues; cost estimator and optional structured LLM proposal/diff workflow |
| 5 — Editorial pass | **Started** | Validated transition model and 5 curated transitions | Roughly 45 more transitions, icons for top ~50, and polished adult/child copy for top ~50 |
| 6 — Web view | **Mostly complete** | Unified FastAPI server, horizontal SVG timeline, geographic lanes, filters/search, era zoom, drawer, sources, relationship navigation, transition connectors | Reviewed collapsible display groups, linked map, stronger mobile/visual testing, authentication before public write access |
| 7 — Print poster | **Not started** | — | A1/A0 SVG renderer, methodology/legend footer, PDF export and print test |
| 8 — Grow with the kid | **Ongoing later work** | Adult/Child selector, extensible text model, period pilot grown to 102 records with role review | Substantial content, more reading levels, language UI, family-history layer |
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

- **4,671** canonical polities (down from 4,794 as the consolidation pass folds duplicate/phase
  records into their parents; up from 4,669 as New Kingdom of Egypt, Nazi Germany, and the
  European Union were added — see below).
- **137** automated tests passing; `build.py` validates **5** curated transitions, **117** periods
  (up from 105), and **102** period links (up from 97).
- Global-tier reference-poster comparison (started in b0acb2e1): **complete**. All 15 flagged
  gaps are now filled — 3 as new weight-bearing polities (New Kingdom of Egypt, Nazi Germany,
  European Union; all `visibility_override: global`, pending the next full
  `compute_prominence.py` run to materialize), and 12 as `periods/*.yaml` context bands with no
  competing weight bar (Vikings, Celts, Etruscans, Mycenaean Greece, Minoan Crete, Indus Valley,
  Olmec, and the Wessex/Norman/Plantagenet/Tudor/Capetian dynasty spans, the last four
  `phase_of`-linked to `kingdom_of_england`/`kingdom_of_france` via `period_links.yaml`).
- Seshat reconciliation: **81 auto**, **223 reviewed decisions applied** (109 accept / 149 reject
  across two review sessions, some records touched twice), **35 review pending**, **34 unmatched**.
- Entity consolidation (new): **333** of 4,669 records triaged — 87 `phase_of`, 44 `same_entity`,
  3 `part_of`, 2 `discarded`, 197 confirmed `independent`; **4,336 still untouched**.
- Wikidata type-eligibility: **5,088** decisions made (3,126 accepted, 14 excluded), but **1,948**
  still flagged `review` — essentially unchanged since last count.
- Entity-type classification (polity/civilization/culture/people/tribe/archaeological_horizon):
  **3,222 pending**.
- Subdivision-parent classification (new): workflow built, only 4 records reviewed so far.
- Period pilot: grown from the original 4-region, 14-record pilot to **102** period records;
  **94 pending** timeline-role review.
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
