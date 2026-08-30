# Histomap — Roadmap

Forward-looking only: what's left to do, and design questions deliberately deferred. For
current implementation status and the build narrative, see [STATUS.md](STATUS.md); for project
context and how to run things, see [README.md](README.md); for the classification system the
dataset is organized around, see [ONTOLOGY.md](ONTOLOGY.md).

---

## Remaining work, in recommended order
1. A detail side-panel on click, matching `/`'s existing panel — informational fields only
  (dates, authority, geography, links), not the editing actions (`/` also lets you edit period
  type, convert to entity, edit geography — those stay on `/` as curation tools; `/explore` is
  a browse view).
2. Disambiguate the 8 same-named period records (4× "Kingdom of Hungary", 2× "Kingdom of
     Poland", 2× "Kingdom of Spain" — distinct historical regimes, currently indistinguishable
     in any list).
3. Correct the `continents` field on 3 mistagged periods
     (`lebanese_republic_under_french_mandate_period`, `state_of_greater_lebanon_period`,
     `state_of_vietnam_period` — all clearly Asian, tagged with 5-6 continents). Root cause not
     yet traced (these carry `authority: "Histomap editorial consolidation"`, not the
     raw-import path behind the `enrich_geography.py` polity bug documented in STATUS.md).
4. Close the matching regional-era coverage gap for `european_iron_age` (raw import with no
     hand-curated era counterpart, unlike its Nile Valley/Fertile Crescent/East Asian peers).
     The Bronze Age and Neolithic clusters are done: `european_bronze_age` (duplicate of
     `european_bronze_age_era`) is retired, and new overarching `bronze_age_era` /
     `neolithic_era` regional eras now parent all regional siblings in both clusters — see
     ONTOLOGY.md's "Overarching regional eras for genuinely cross-regional themes."
5. **Close out Seshat reconciliation** — only 69 records left (35 review + 34 unmatched); the
   cheapest queue left to finish. Review decisions are durable and must not be overwritten by
   pipeline reruns.
6. **Drive down the consolidation queue** (4,336 of 4,669 untriaged) — now the largest backlog and
   the most direct lever on "noisy entities before expanding the default view," given the
   duplicate/phase-record rate found in the 333 already reviewed.
7. **Resolve the 1,948 stuck Wikidata type-eligibility flags** and the 3,222-record entity-type
   classification queue — the other half of "reduce noisy entities," and unmoved since the last
   snapshot.
8. **Run a comprehensive polity → period reclassification pass.** The `/period-review` queue
   (`reports/period_role_review.jsonl`) already handles this decision — a polity whose
   `timeline_role` should be `period` or `both`, because it's really a cultural sequence,
   archaeological horizon, or context span rather than a weight-bearing political entity — but
   it currently only covers 94 records queued from whatever originally seeded it. Look at the
   full polity set (4,671 records), not just that existing queue, for more candidates the
   original seeding missed. Note that `Polity.entity_type` already distinguishes
   civilization/culture/people/tribe/archaeological_horizon from plain `polity` — this pass is
   as much about applying that field consistently (it's currently under-used) as it is about
   generating new `periods/*.yaml` records; a record correctly typed `entity_type: civilization`
   but still living as a weight-bearing polity band is itself a candidate for this queue.
9. **Introduce historical polygons** from Seshat/Cliopatria, then recompute geography and weights.
10. **Accept display groups** for major historical sequences and expose collapse/expand behavior.
11. **Complete the top-50 editorial pass:** descriptions, icons, and the most important transitions.
12. **Add the linked map**, followed by the print SVG/PDF pipeline.
13. Treat LLM proposals as optional acceleration after estimating cost; the human review decisions and
   canonical YAML remain authoritative.

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
- **Civilization/culture as a separate visual lane on `/explore`**, positioned under the
  Period row rather than mixed into it — `entity_type: civilization`/`culture` polities and
  `periods/*.yaml` records both currently render alongside plain historical periods with no
  visual distinction. Raised in conversation, not yet scoped into a plan. **Revisit** together
  with item 4 above (the polity → period reclassification pass) — the two are related: a
  clean reclassification pass makes it obvious which records would populate this lane.
