# Histomap — Roadmap

Forward-looking only: what's left to do, and design questions deliberately deferred. For
current implementation status and the build narrative, see [STATUS.md](STATUS.md); for project
context and how to run things, see [README.md](README.md); for the classification system the
dataset is organized around, see [ONTOLOGY.md](ONTOLOGY.md).

---

## Remaining work, in recommended order

0. **Consider retiring the `/` Timeline page** (and any pipeline/server logic that exists only to
    support it) if `/explore` has fully superseded it and nothing else depends on that code path.
    The "browse vs. curate" line that used to justify keeping `/` around has partly dissolved:
    `web/explore_details.js` is no longer read-only (see STATUS.md) — it now covers entity-type/
    period-kind edits, polity↔period conversion, and a general raw-field editor, reusing most of
    the same endpoints `/`'s own drawer calls. What's left to actually check before deleting
    anything: whether `/`'s geography editor and any other still-`/`-only affordance have a
    `/explore` equivalent yet, and whether any server route is `/`-only-reachable in practice.
1. Do a proper `/simplify` pass to see what could be removed, trimmed, simplified: dead code,
   convoluted logic, very similar data concepts that could be merged, etc.
2. **Close out Seshat reconciliation** — only 69 records left (35 review + 34 unmatched); the
   cheapest queue left to finish. Review decisions are durable and must not be overwritten by
   pipeline reruns.
3. **Drive down the consolidation queue** (4,336 of 4,669 untriaged) — now the largest backlog and
   the most direct lever on "noisy entities before expanding the default view," given the
   duplicate/phase-record rate found in the 333 already reviewed.
4. **Resolve the 1,948 stuck Wikidata type-eligibility flags** and the 3,222-record entity-type
   classification queue — the other half of "reduce noisy entities," and unmoved since the last
   snapshot.
5. **Run a comprehensive polity → period reclassification pass.** The consolidation review
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
6. **Introduce historical polygons** from Seshat/Cliopatria, then recompute geography and weights.
7. **Accept display groups** for major historical sequences and expose collapse/expand behavior.
8. **Complete the top-50 editorial pass:** descriptions, icons, and the most important transitions.
9. **Add the linked map**, followed by the print SVG/PDF pipeline.
10. Treat LLM proposals as optional acceleration after estimating cost; the human review decisions
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
- **Add a lane for main events** -- the specific events that define the start/end of an
  era, chapter, or period, starting with those. Today a boundary (e.g. Bronze Age
  Collapse ending Mesopotamian Early States) is only implicit in a record's `start`/`end`
  dates; there's no explicit event entity a viewer can click to see what happened, or
  that a `start_confidence`/`end_confidence` figure can point back to as its actual
  source. Needs its own design pass: a new entity/schema for events, how an era/chapter/
  period would reference "the event that ends me," and how `/explore` would display a
  thin events lane against the existing chapter/era/period rows.
