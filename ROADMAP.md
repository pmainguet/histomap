# Histomap — Roadmap

Forward-looking only: what's left to do, and design questions deliberately deferred. For
current implementation status and the build narrative, see [STATUS.md](STATUS.md); for project
context and how to run things, see [README.md](README.md); for the classification system the
dataset is organized around, see [ONTOLOGY.md](ONTOLOGY.md).

---

## Remaining work, in recommended order

0. **Close the residual geography gaps.** Four passes done 3 September 2026 (see STATUS.md):
   country-code table growth, a centroid-resolved-country-but-empty-continents bug fix, a new
   Wikidata-relationship-neighbor continent inference, and two name-cluster fixes (Taifa/Saxe).
   No-continent count: 917 → 826; country-not-in-region-table count: 73 → 2 (the 2 remaining are
   deliberately unclassified 21st-century Antarctica-claim micronations, not real historical
   polities). **What's left:**
   - **A Seshat geography extraction** (see the write-up below) -- the next concrete, already-
     scoped lever, expected to close on the order of 45 more records outright.
   - After that, a genuine long tail of low-count, obscure-or-ambiguous polities with no
     Wikidata geography of any kind and no Seshat coverage either -- ordinary manual review,
     same as any other queue, unless a new signal turns up.

   **Seshat geography extraction -- what should be done:** `sources/seshat_polities.parquet`
   already carries a `world_region` field (10 values: Africa, CentralEurasia, EastAsia, Europe,
   NorthAmerica, Oceania-Australia, SouthAmerica, SouthAsia, SoutheastAsia, SouthwestAsia) and a
   finer `ngas` (Natural Geographic Area) list per polity -- neither is wired into geography today.
   Confirmed live, 3 September 2026: 45 of the 110 no-Wikidata-QID gap records already carry an
   `external_ids.seshat` code that matches this parquet's `seshat_id` directly (no fuzzy matching
   needed for those). Plan:
   1. Add a small `world_region -> continent` table (10 entries -- straightforward for 9 of them;
      `CentralEurasia` needs an editorial call, since Seshat's steppe/Central-Asian world region
      doesn't map cleanly onto a single continent bucket the way the others do).
   2. Join it onto any polity whose `external_ids.seshat` matches a `seshat_id` in the parquet,
      same "only fill what's missing, respect `manual_overrides`" convention as every other pass
      in `pipeline/enrich_geography.py`. Closes ~45 records outright.
   3. `sources/seshat_crosswalk.parquet` (`seshat_id -> polity_id`, built for the Phase 2 Seshat
      reconciliation overlay) covers a handful more (5, confirmed live) that lack an
      `external_ids.seshat` entry of their own but are still linked via that crosswalk -- join it
      as a fallback.
   4. The remaining ~65 no-QID records have no Seshat link at all yet -- closing those would need
      a name-match pass against `seshat_polities.parquet`'s `canonical_name`/`long_name` (the same
      "dry-run, review every match by hand" discipline `seed_present_countries_from_name.py` and
      `infer_continent_from_relationships.py` used, given the real false-positive risk that
      discipline has already caught twice this session).
   5. `ngas` could, in principle, also feed a country/historical_region-level signal (finer than
      `world_region`), but that needs its own, larger curated NGA -> country/region table (Seshat
      has several dozen NGAs, not 10) -- a stretch goal past the continent-closing win above, not
      part of this immediate plan.
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
