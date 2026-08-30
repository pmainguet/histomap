# Histomap — Roadmap

Forward-looking only: what's left to do, and design questions deliberately deferred. For
current implementation status and the build narrative, see [STATUS.md](STATUS.md); for project
context and how to run things, see [README.md](README.md); for the classification system the
dataset is organized around, see [ONTOLOGY.md](ONTOLOGY.md).

---

## Remaining work, in recommended order
1. **Resolved 2026-08-30:** disambiguated the same-named period records — actually 9, not 8
   (4× "Kingdom of Hungary", 3× "Kingdom of Poland", 2× "Kingdom of Spain" — the "8" count
   was stale, Poland has 3 not 2). Wikidata's own English labels are identical across each
   group too (only the descriptions differ), so used a verified `(start–end)` date-range
   parenthetical for each — the same disambiguation convention `polities/
   kingdom_of_hungary_10001301.yaml` (canonical_name "Kingdom of Hungary (1000–1301)")
   already established. Note: `kingdom_of_poland_q577867_period` (1025–1385) and
   `kingdom_of_poland_q3446214_period` (1320–1386) overlap heavily and may describe the
   same underlying continuity under two Wikidata items — a possible future
   consolidation candidate, not acted on here (out of scope for a naming fix).
2. **Resolved 2026-08-30:** corrected the `continents` field on the 3 mistagged periods
   (`lebanese_republic_under_french_mandate_period`, `state_of_greater_lebanon_period`,
   `state_of_vietnam_period` — all clearly Asian, were tagged with 5-6 continents), and
   traced the root cause: `server/app.py`'s consolidation-review "retire and generate a
   period" endpoint (`~line 663`) copies the source polity's `geography` block verbatim
   into the new period record — not a bug in that copy itself, but a carrier for
   `enrich_geography.py`'s still-open Bug B (documented in STATUS.md) whenever the source
   polity's own geography was already poisoned before being retired. Confirms Bug B's
   blast radius extends to consolidation-generated periods, not just polities; still needs
   its own fix pass.
3. **Resolved 2026-08-30:** closed the regional-era coverage gap for `european_iron_age` —
   it had no `broader_periods` at all (a bare, unparented period). Rather than promote it to
   its own `regional_era` (which would have duplicated `mediterranean_classical_era`'s
   near-identical geographic/temporal scope for the same macro chapter), nested it as
   `tier: period` under `mediterranean_classical_era` instead — matching the day's other
   bare-period fixes (Old Kingdom of Egypt under Egypt's era, Uruk period under
   Mesopotamia's). The Bronze Age and Neolithic clusters were already done: `european_bronze_age`
   (duplicate of `european_bronze_age_era`) is retired, and new overarching `bronze_age_era` /
   `neolithic_era` regional eras now parent all regional siblings in both clusters — see
   ONTOLOGY.md's "Overarching regional eras for genuinely cross-regional themes."
3 bis. The "kingdom ...", "crown", "house" entries in period should be moved to polities, but maybe some period could be derived from some, to be seen -- **note (2026-08-30):** the closely related "Republic of"/"Reign of" subset (15 records) is done, see below; this broader "kingdom/crown/house" set is intentionally left as-is for now, since some of it (the House of Wessex/Plantagenet/Tudor dynasty-span periods specifically) was a deliberate earlier design choice (dynasty spans as context bands under the continuously-existing Kingdom of England/France polities, not separate countries in their own right) rather than a mistake to reverse.
4. Review the whole review workspace to see if it's still aligned with the way we do things
   given the recent changes. In particular, we should be able to switch an entity from era,
   period, civilization, polity, etc and link things correctly. But maybe that's only to be
   added in the side panel (now built, informational only — see STATUS.md), to be seen.
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
   **Constraint:** `prominence_score` ranks polities against each other (most-to-least prominent,
   scoped by region) for display purposes only — it must never be a signal for `entity_type` or
   `timeline_role` classification. Those decisions come from Wikidata type evidence and editorial
   judgment, not from how prominent or well-documented a record happens to be.
   **Resolved 2026-08-30:** a suspected polity/period duplication (`egyptian_old_kingdom`/
   `old_kingdom_of_egypt` and their Middle Kingdom counterparts) triggered a full-dataset audit
   for the same shape (period ↔ polity sharing a Wikidata QID). 91 candidates found; only the
   Egypt pair was a genuine duplicate (removed, in favor of the already-complete polity
   records) — the other 90 turned out to be two legitimate, different mechanisms (auto-promoted
   dormant polities and consolidation-review-retired polities). See ONTOLOGY.md's "Polity/period
   duality: link, don't duplicate" for the full pattern and the audit's outcome.
   **Follow-up, same day:** on review, 16 of those 91 (`mamluk_sultanate_of_egypt` plus 15
   "Republic of"/"Reign of" consolidation-retired records — Cuba, Egypt, Venezuela, Sudan ×2,
   Congo ×2, Afghanistan, Albania, Austria, Burma, Georgia, Equatorial Guinea, Seychelles,
   Amadeo I of Spain) turned out to be genuinely distinct, narrower regime-phases within a
   much broader "the country across all eras" umbrella polity (e.g. "Republic of Egypt"
   1953-1958 vs. "Egypt" 1922-present) — the same relationship as the just-disambiguated
   Kingdom of Hungary/Poland/Spain phases, not a duplicate at all. Restored as independent
   polities from their pre-deletion git history, their now-redundant period companions
   removed. Also found and fixed along the way: `aztec_triple_alliance_period` (an actual
   duplicate of the already-weight-bearing `aztec_empire` polity, which even lists "Triple
   Alliance" as an alias — deleted); `dacia` renamed to "Dacian Kingdom" and reclassified
   `entity_type: polity` (it had a real unified political actor, unlike the Civilizations &
   Cultures lane's other residents); and the Civilizations & Cultures lane gained a second,
   more reliable routing signal (`CIVILIZATION_BACKDROP_AUTHORITY`) after discovering
   `ancient_egypt_period`/`babylonia_period`/`chinese_empire_period` had silently fallen out
   of the lane once their source polities were deleted in the audit above.
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
