# Histomap — Roadmap

Forward-looking only: what's left to do, and design questions deliberately deferred. For
current implementation status and the build narrative, see [STATUS.md](STATUS.md); for project
context and how to run things, see [README.md](README.md); for the classification system the
dataset is organized around, see [ONTOLOGY.md](ONTOLOGY.md).

---

## Remaining work, in recommended order

1. **Work the polity → period reclassification queue (98 pending, `/consolidation-review`'s
   "period"/"both" decision).** The comprehensive full-polity-set scan this item called for is
   done (31 August 2026, see STATUS.md): re-running `pipeline/classify_period_roles.py`'s
   existing Wikidata-ancestry signal across all 4,697 polities found the queue essentially
   unchanged (94 -> 80 candidates, so the original seeding wasn't actually missing much), and a
   new second signal -- entity_type already civilization/culture/people/tribe/
   archaeological_horizon but still `timeline_role: entity` -- added 23 more (Babylonia, Maya
   civilization, Gaelic Ireland, Xiongnu, and others). Both signals only *queue* candidates for a
   human period/both decision, never auto-convert on the entity_type signal alone (entity_type
   being confirmed doesn't mean period-vs-entity modeling was decided -- Babylonia is a
   documented case of "confirmed civilization, deliberately kept weight-bearing"). What's left is
   ordinary manual review of the 98.
   **Constraint:** `prominence_score` ranks polities against each other (most-to-least prominent,
   scoped by region) for display purposes only — it must never be a signal for `entity_type` or
   `timeline_role` classification. Those decisions come from Wikidata type evidence and editorial
   judgment, not from how prominent or well-documented a record happens to be.
2. **Introduce historical polygons** from Seshat/Cliopatria, then recompute geography and weights.
3. **Complete the top-50 editorial pass:** descriptions, icons, and the most important transitions.
4. **Add the linked map**, followed by the print SVG/PDF pipeline.
5. **Work the Wikidata type-eligibility (661) and entity-type classification (2,682) queues** --
   down from 1,948/3,098 after a 31 August 2026 rules-table expansion closed a large,
   genuinely-not-ambiguous gap (see STATUS.md). No further safe automation identified: ~350 of
   the remaining eligibility flags are modern administrative subdivisions correctly gated behind
   `/subdivision-review`'s parent-confirmation step, and the rest is a long tail of low-count,
   genuinely ambiguous or obscure types -- ordinary manual review from here, same as any other
   queue.
6. **Close the residual geography gaps** left after the 31 August 2026 continent/region fixes (see
   STATUS.md): **986** active polities still have no continent at all (no Wikidata QID, or a QID
   with neither a usable P17 chain nor a direct P30 claim nor a centroid -- every signal built so
   far has been tried and come up empty; needs a different approach, if one exists); **69** have
   `present_countries` but their country isn't yet in `pipeline/historical_regions.py`'s
   ~180-country starter table (cheap and safe to grow incrementally).
7. **Audit of remaining heuristic/on-the-fly computations — complete (31 August 2026, see
   STATUS.md); decide which to act on.** Two real gaps found, plus a curation-backlog issue,
   plus a "fine as-is" set:
   - **Macro-chapter placement** (`best_chapter_for_polity` in `pipeline/build_explore_tree.py`)
     decides which of the 9 chapters a civ/culture/people/tribe entity or ordinary polity lands
     in, by pure date overlap, with **no override field at all** — structurally identical to what
     `linked_era_id` used to be. Candidate for a new `linked_chapter_id` field, seeded the same
     way (`pipeline/seed_linked_era_ids.py` is the template).
   - **Civilizations & Cultures lane membership for periods** (`_is_civilization_lane_period`)
     falls back to a name-substring guess ("civilization"/"culture" in the canonical name) when
     the one real signal (`authority == CIVILIZATION_BACKDROP_AUTHORITY`, a magic string smuggled
     into a free-text field) isn't set. Candidate for a real `Period.civilization_lane` field.
   - **Period → regional-era placement** (`rank_candidates` in `build_explore_tree.py`) already
     has an override field (`Period.broader_periods`) — this is a curation backlog, not a missing
     field. Best fixed with a one-shot seeding pass, same recipe as `seed_linked_era_ids.py`.
   - Everything else audited (subdivision-parent suggestions, consolidation fuzzy-matching,
     geography gap-filling, search ranking, entity-type P279-ancestry inference, automatic
     period-role conversion) is already proposal-only behind a real human-confirmation step, or
     already a stored+override-gated field — fine as pure heuristics, no action needed.
8. **A period can subdivide a civilization/polity, not just an era — the schema and tree only
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
9. **Add a lane for main events** -- the specific events that define the start/end of an
   era, chapter, or period, starting with those. Today a boundary (e.g. Bronze Age
   Collapse ending Mesopotamian Early States) is only implicit in a record's `start`/`end`
   dates; there's no explicit event entity a viewer can click to see what happened, or
   that a `start_confidence`/`end_confidence` figure can point back to as its actual
   source. Needs its own design pass: a new entity/schema for events, how an era/chapter/
   period would reference "the event that ends me," and how `/explore` would display a
   thin events lane against the existing chapter/era/period rows.
10. **Split `Period` into separate `MacroChapter`/`RegionalEra`/`Period` Pydantic
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
