# Histomap — Roadmap

Forward-looking only: what's left to do, and design questions deliberately deferred. For
current implementation status and the build narrative, see [STATUS.md](STATUS.md); for project
context and how to run things, see [README.md](README.md); for the classification system the
dataset is organized around, see [ONTOLOGY.md](ONTOLOGY.md).

---

## Remaining work, in recommended order

0. **Fix the polity ↔ period conversion friction.** Converting one to the other today isn't a
   field flip -- it's a structural migration: a new record with a new id gets created in the
   *other* directory (`polities/` ↔ `periods/`) and the original is retired, rather than the
   same record just changing what it is. Surfaced live, 3 September 2026, while reclassifying
   `seshat_kachi_plain_pkceran` as a period. Needs its own brainstorm/design pass (approaches,
   tradeoffs, a real spec) before touching anything -- not a quick fix.
0 bis. **Merge `subdivision` (the `entity_type` + `parent` + `subdivision_parent_status`
   mechanism) into `detail_of`.** Raised live, 3 September 2026: a subdivision is conceptually
   the same "this entity nests inside that one" relationship `detail_of` already covers (the
   September 1 merge folded `phase_of` *and* `part_of` into it) -- `subdivision`/`parent` is a
   third, separate, older mechanism expressing the same idea. `/subdivision-review`, the review
   UI that used to confirm a subdivision's parent, was removed the same day (see STATUS.md) with
   `build.py`'s publish-gate on `subdivision_parent_status` relaxed in the meantime (everything
   publishes now, unconfirmed or not) -- this item is the real, deferred fix: fold the
   subdivision concept into `detail_of` properly rather than leave two mechanisms doing the same
   job. Needs its own design pass.
1. **Work the polity → period reclassification queue (73 pending, confirmed live 1 September 2026,
   `/consolidation-review`'s "period"/"both" decision).** Full scope-and-seed pass done (see
   STATUS.md); what's left is ordinary manual review.
   **Constraint:** `prominence_score` ranks polities against each other (most-to-least prominent,
   scoped by region) for display purposes only — it must never be a signal for `entity_type` or
   `timeline_role` classification. Those decisions come from Wikidata type evidence and editorial
   judgment, not from how prominent or well-documented a record happens to be.
2. **Introduce historical polygons** from Seshat/Cliopatria, then recompute geography and weights.
3. **Complete the top-50 editorial pass:** descriptions, icons, and the most important transitions.
4. **Add the linked map**, followed by the print SVG/PDF pipeline.
5. **Work the Wikidata type-eligibility (655) and entity-type classification (2,677) backlogs.**
   (confirmed live 1 September 2026 -- see STATUS.md for how they got here). `/type-review` and
   `/subdivision-review`, the dedicated queue UIs, were removed 3 September 2026 (see STATUS.md);
   per-record classification still happens via `/explore`'s side panel ("Set entity type" /
   the raw-fields editor) instead of a batch queue. No further safe automation identified: ~350
   of the remaining eligibility flags are modern administrative subdivisions, and the rest is a
   long tail of low-count, genuinely ambiguous or obscure types -- ordinary manual review from
   here, same as any other queue.
7. **A period can subdivide a civilization/polity, not just an era — the schema and tree only
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
8. **Add a lane for main events** -- the specific events that define the start/end of an
   era, chapter, or period, starting with those. Today a boundary (e.g. Bronze Age
   Collapse ending Mesopotamian Early States) is only implicit in a record's `start`/`end`
   dates; there's no explicit event entity a viewer can click to see what happened, or
   that a `start_confidence`/`end_confidence` figure can point back to as its actual
   source. Needs its own design pass: a new entity/schema for events, how an era/chapter/
   period would reference "the event that ends me," and how `/explore` would display a
   thin events lane against the existing chapter/era/period rows.
9. **Split `Period` into separate `MacroChapter`/`RegionalEra`/`Period` Pydantic
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
10. Add a way to ask a LLM about it's take on whether an entity is a separate or details of or the same entity. Would like to have a chat appearing on the side of the (http://127.0.0.1:8000/consolidation-review) so that it can take the different information, look at the wikipedia pages and give it's own take via a short (but explained) answer. I should be able to ask following question if needed, like in a chat, but the first should be click on a button, he get the info and the question and answer right away 
