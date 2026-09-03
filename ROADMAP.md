# Histomap — Roadmap

Forward-looking only: what's left to do, and design questions deliberately deferred. For
current implementation status and the build narrative, see [STATUS.md](STATUS.md); for project
context and how to run things, see [README.md](README.md); for the classification system the
dataset is organized around, see [ONTOLOGY.md](ONTOLOGY.md).

---

## Remaining work, in recommended order

0. **Close the residual geography gaps.** Five passes done 3 September 2026 (see STATUS.md):
   country-code table growth, a centroid-resolved-country-but-empty-continents bug fix, a new
   Wikidata-relationship-neighbor continent inference, two name-cluster fixes (Taifa/Saxe), and a
   Seshat `world_region` extraction (`pipeline/enrich_geography_from_seshat.py`) for records with no
   Wikidata QID at all. No-continent count: 917 → 781; country-not-in-region-table count: 73 → 2
   (the 2 remaining are deliberately unclassified 21st-century Antarctica-claim micronations, not
   real historical polities). **What's left**, no further safe automation identified:
   - A name-match pass against `seshat_polities.parquet`'s `canonical_name`/`long_name` for the
     ~65 no-QID records with no `external_ids.seshat` link at all -- same "dry-run, review every
     match by hand" discipline `seed_present_countries_from_name.py` and
     `infer_continent_from_relationships.py` used, given the real false-positive risk that
     discipline has already caught twice this session. Not attempted yet -- fuzzier and riskier
     than the direct-id join `enrich_geography_from_seshat.py` already does.
   - `ngas` (Seshat's finer Natural Geographic Area, one level below `world_region`) could, in
     principle, feed a country/historical_region-level signal too, but needs its own, larger
     curated NGA → country/region table (Seshat has several dozen NGAs, not 10) -- a stretch goal,
     not attempted.
   - Past those two, a genuine long tail of low-count, obscure-or-ambiguous polities with no
     Wikidata geography of any kind and no Seshat coverage either -- ordinary manual review, same
     as any other queue, unless a new signal turns up.
0 bis. In consolidation review, entity that only matches on "Mandate", "Government", "Canton", etc) and have non country names or adjectives (or other derivatives), unless they are very close geographically should not be considered as possible matches. This needs to be strenghthen, i gave you some examples in the conversation directly
0 ter. remove in the review section the Classify entities and Links subdivisions workflow/code/etc
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
5. **Work the Wikidata type-eligibility (655) and entity-type classification (2,677) queues**
   (confirmed live 1 September 2026 -- see STATUS.md for how they got here). No further safe
   automation identified: ~350 of the remaining eligibility flags are modern administrative
   subdivisions correctly gated behind `/subdivision-review`'s parent-confirmation step, and the
   rest is a long tail of low-count, genuinely ambiguous or obscure types -- ordinary manual review
   from here, same as any other queue.
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
