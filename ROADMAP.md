# Histomap — Roadmap

Forward-looking only: what's left to do, and design questions deliberately deferred. For
current implementation status and the build narrative, see [STATUS.md](STATUS.md); for project
context and how to run things, see [README.md](README.md); for the classification system the
dataset is organized around, see [ONTOLOGY.md](ONTOLOGY.md).

---

## Remaining work, in recommended order

1. **Introduce historical polygons** from Seshat/Cliopatria, then recompute geography and weights.
2. **Complete the top-50 editorial pass:** descriptions, icons, and the most important transitions.
3. **Add the linked map**, followed by the print SVG/PDF pipeline.
4. **Work the Wikidata type-eligibility (655) and entity-type classification (2,677) backlogs.**
   (confirmed live 1 September 2026 -- see STATUS.md for how they got here). `/type-review` and
   `/subdivision-review`, the dedicated queue UIs, were removed 3 September 2026 (see STATUS.md);
   per-record classification still happens via `/explore`'s side panel ("Set entity type" /
   the raw-fields editor) instead of a batch queue. No further safe automation identified: ~350
   of the remaining eligibility flags are modern administrative subdivisions, and the rest is a
   long tail of low-count, genuinely ambiguous or obscure types -- ordinary manual review from
   here, same as any other queue.
   **Constraint:** `prominence_score` ranks polities against each other (most-to-least prominent,
   scoped by region) for display purposes only — it must never be a signal for `entity_type` or
   `timeline_role` classification. Those decisions come from Wikidata type evidence and editorial
   judgment, not from how prominent or well-documented a record happens to be.
5. **Add a lane for main events** -- the specific events that define the start/end of an
   era, chapter, or period, starting with those. Today a boundary (e.g. Bronze Age
   Collapse ending Mesopotamian Early States) is only implicit in a record's `start`/`end`
   dates; there's no explicit event entity a viewer can click to see what happened, or
   that a `start_confidence`/`end_confidence` figure can point back to as its actual
   source. Needs its own design pass: a new entity/schema for events, how an era/chapter/
   period would reference "the event that ends me," and how `/explore` would display a
   thin events lane against the existing chapter/era/period rows.
