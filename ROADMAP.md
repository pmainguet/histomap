# Histomap — Roadmap

Forward-looking only: what's left to do, and design questions deliberately deferred. For
current implementation status and the build narrative, see [STATUS.md](STATUS.md); for project
context and how to run things, see [README.md](README.md); for the classification system the
dataset is organized around, see [ONTOLOGY.md](ONTOLOGY.md).

---

## Remaining work, in recommended order

0. **Still not safe to retire `/` — the 2 blocking gaps are closed, 3 steps remain.** Audited 31
   August 2026 (see STATUS.md); both blocking gaps (geography editing, viewing curated
   transitions) are now built into `/explore`'s side panel, same day. What's left of the original
   5-step order: (3) decide on the remaining non-blocking-but-real gaps — free-text entity search,
   visibility-tier/entity-type/period-kind filters, the named-period picker + `?era=` deep link,
   era presets/manual date-range input, relationship highlighting on the chart, swimlane
   collapse/expand, and keyboard-operable bands (`/explore`'s `bandRect` sets no `tabindex`/keydown
   handling at all) — build or explicitly accept the loss for each; (4) update README.md (still
   calls `/` the primary workspace root) and the `/reviews`-family nav links (all link to `/`,
   would 404); (5) only then delete `GET /` and `web/index.html`/`web/app.js`.
1. **Close out Seshat reconciliation** — only 69 records left (35 review + 34 unmatched); the
   cheapest queue left to finish. Review decisions are durable and must not be overwritten by
   pipeline reruns.
2. **Drive down the consolidation queue** (4,336 of 4,669 untriaged) — now the largest backlog and
   the most direct lever on "noisy entities before expanding the default view," given the
   duplicate/phase-record rate found in the 333 already reviewed.
3. **Resolve the 1,948 stuck Wikidata type-eligibility flags** and the 3,222-record entity-type
   classification queue — the other half of "reduce noisy entities," and unmoved since the last
   snapshot.
4. **Run a comprehensive polity → period reclassification pass.** The consolidation review
   queue's "period"/"both" decision (`/consolidation-review`, backed by
   `reports/period_role_review.jsonl` for the `period_kinds` it seeds) already handles this
   decision — a polity whose `timeline_role` should be `period` or `both`, because it's really a
   cultural sequence, archaeological horizon, or context span rather than a weight-bearing
   political entity — but it currently only covers 94 records queued from whatever originally
   seeded it. Look at the full polity set (4,671 records), not just that existing queue, for more
   candidates the original seeding missed. Note that `Polity.entity_type` already distinguishes
   civilization/culture/people/tribe/archaeological_horizon from plain `polity` — this pass is
   as much about applying that field consistently (it's currently under-used) as it is about
   generating new `periods/*.yaml` records; a record correctly typed `entity_type: civilization`
   but still living as a weight-bearing polity band is itself a candidate for this queue.
   **Constraint:** `prominence_score` ranks polities against each other (most-to-least prominent,
   scoped by region) for display purposes only — it must never be a signal for `entity_type` or
   `timeline_role` classification. Those decisions come from Wikidata type evidence and editorial
   judgment, not from how prominent or well-documented a record happens to be.
5. **Introduce historical polygons** from Seshat/Cliopatria, then recompute geography and weights.
6. **Accept display groups** for major historical sequences and expose collapse/expand behavior.
7. **Complete the top-50 editorial pass:** descriptions, icons, and the most important transitions.
8. **Add the linked map**, followed by the print SVG/PDF pipeline.
9. Treat LLM proposals as optional acceleration after estimating cost; the human review decisions
   and canonical YAML remain authoritative.

## Ideas / deferred design questions

Considered, deliberately not done, with the concrete trigger for revisiting:

- **Split `Period` into separate `MacroChapter`/`RegionalEra`/`Period` Pydantic
  classes** instead of one `Period` class discriminated by `tier`. Would trade runtime
  validation (Task 2's `validate_period_tiers()` in the period-ontology plan) for
  structural safety (a macro chapter simply couldn't have a `broader_periods` value).
  Not done because it breaks the precedent this schema already set twice
  (`Polity.entity_type`, `Period.kind` — one class, an enum discriminator, several
  flavors) and would complicate `pipeline/period_hierarchy.py`'s tree-walking, which
  currently works because every tier shares one shape. **Revisit if** a field ever needs
  to exist on `macro_chapter` or `regional_era` that would be actively wrong (not just
  unused) on a regular `period` — at that point, Pydantic discriminated unions
  (`Annotated[Union[...], Field(discriminator="tier")]`) would give both the safety and
  a workable `PeriodHierarchy`. See `ONTOLOGY.md` for the full period-tier design.
- **A period can subdivide a civilization/polity, not just an era — the schema and tree only
  support the latter today.** Surfaced by `early_dynastic_mesopotamia`: conceptually it's a
  phase *of Sumer* (the civilization), the same relationship Old Kingdom of Egypt has to
  Ancient Egypt or Old Babylonian Empire has to Babylonia — but `broader_periods` only
  resolves against era-tier periods for tree placement, so today that relationship can only
  be expressed via `period_links.yaml`'s `context` relation, which doesn't affect *where the
  period nests in the tree* the way `broader_periods` does. Two structurally different kinds
  of "period subdivision" (era-subdivision vs. civilization/polity-subdivision) are currently
  conflated into one mechanism. Needs its own design pass: what should the schema/tree
  support, and how should `/explore` display the distinction (a sub-lane under the
  civilization/polity's own band, rather than nested in the ordinary Period row)?
- **Audit remaining heuristic/on-the-fly computations that affect how polities, civilizations,
  etc. are classified or displayed, and decide which deserve to become explicit persisted
  fields.** `linked_era_id` was exactly this kind of thing until 31 August 2026 — it used to be
  recomputed on every build by `_linked_era_id()`'s `rank_candidates()` heuristic in
  `pipeline/build_explore_tree.py`, silently changing depending on data elsewhere in the set, with
  no way to correct a bad match short of fighting the heuristic. It's now a plain stored field,
  seeded once and editable directly. Other candidates likely exist in the same file and in
  `pipeline/geography_overlap.py`/`pipeline/period_hierarchy.py` (e.g. period tree placement via
  `broader_periods` + `rank_candidates`, prominence-driven display ordering) — worth listing them
  out explicitly so each can be judged on its own merits rather than assumed fine by default.
- **Add a lane for main events** -- the specific events that define the start/end of an
  era, chapter, or period, starting with those. Today a boundary (e.g. Bronze Age
  Collapse ending Mesopotamian Early States) is only implicit in a record's `start`/`end`
  dates; there's no explicit event entity a viewer can click to see what happened, or
  that a `start_confidence`/`end_confidence` figure can point back to as its actual
  source. Needs its own design pass: a new entity/schema for events, how an era/chapter/
  period would reference "the event that ends me," and how `/explore` would display a
  thin events lane against the existing chapter/era/period rows.
