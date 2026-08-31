# Histomap — Roadmap

Forward-looking only: what's left to do, and design questions deliberately deferred. For
current implementation status and the build narrative, see [STATUS.md](STATUS.md); for project
context and how to run things, see [README.md](README.md); for the classification system the
dataset is organized around, see [ONTOLOGY.md](ONTOLOGY.md).

---

## Remaining work, in recommended order

0. **Resolve the remaining Wikidata type-eligibility flags (661) and entity-type classification
   queue (2,682 pending, confirmed live)** — down from 1,948/3,098 after a 31 August 2026
   rules-table expansion closed a large, genuinely-not-ambiguous gap in `pipeline/
   wikidata_types.toml`/`backfill_entity_types.py` (see STATUS.md for the analysis). What's left
   in both queues is now the harder tail: modern administrative subdivisions (deliberately
   routed to `/subdivision-review` instead), a handful of generically ambiguous Wikidata types
   ("region," "disputed territory"), and cases needing real per-record judgment — the other half
   of "reduce noisy entities."
1. **Run a comprehensive polity → period reclassification pass.** The consolidation review
   queue's "period"/"both" decision (`/consolidation-review`, backed by
   `reports/period_role_review.jsonl` for the `period_kinds` it seeds) already handles this
   decision — a polity whose `timeline_role` should be `period` or `both`, because it's really a
   cultural sequence, archaeological horizon, or context span rather than a weight-bearing
   political entity — but it currently only covers the 94 records originally seeded into that
   queue (76 of those still open as of 31 August 2026, confirmed live). Look at the full polity set
   (**4,697 records**, confirmed 31 August 2026 after importing the 34 Seshat unmatched drafts —
   see STATUS.md), not just that existing queue, for more candidates the original seeding missed.
   Note that `Polity.entity_type` already distinguishes civilization/culture/people/tribe/
   archaeological_horizon from plain `polity` — this pass is as much about applying that field
   consistently (it's currently under-used) as it is about generating new `periods/*.yaml`
   records; a record correctly typed `entity_type: civilization` but still living as a
   weight-bearing polity band is itself a candidate for this queue.
   **Constraint:** `prominence_score` ranks polities against each other (most-to-least prominent,
   scoped by region) for display purposes only — it must never be a signal for `entity_type` or
   `timeline_role` classification. Those decisions come from Wikidata type evidence and editorial
   judgment, not from how prominent or well-documented a record happens to be.
2. **Introduce historical polygons** from Seshat/Cliopatria, then recompute geography and weights.
4. **Complete the top-50 editorial pass:** descriptions, icons, and the most important transitions.
5. **Add the linked map**, followed by the print SVG/PDF pipeline.

## Ideas / deferred design questions

Considered, deliberately not done, with the concrete trigger for revisiting:

- **A `government_form`/`polity_subtype` field on `Polity`, distinct from `entity_type`.**
  Surfaced 31 August 2026 while expanding `wikidata_types.toml`'s eligibility rules: sultanate,
  khanate, duchy, principality, emirate, beylik, protectorate, vassal state, etc. are all
  conceptually distinct kinds of governed political entity, but the schema's `entity_type` enum
  is flat (`polity`/`civilization`/`subdivision`/`micronation`/`culture`/`people`/`tribe`/
  `archaeological_horizon`) with no room to record which — every one of them just becomes
  `entity_type: polity`, the same as `empire` or `kingdom` already do. Needs its own design pass:
  is this free text or a controlled vocabulary, does it live on `Polity` directly or as a
  `notes`-adjacent field, does `/explore` ever display or filter by it? **Revisit if** this
  distinction becomes something a viewer would actually want to see or filter on, not just an
  internal classification nicety.
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
