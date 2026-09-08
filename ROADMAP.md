# Histomap — Roadmap

Forward-looking only: what's left to do, and design questions deliberately deferred. For
current implementation status and the build narrative, see [STATUS.md](STATUS.md); for project
context and how to run things, see [README.md](README.md); for the classification system the
dataset is organized around, see [ONTOLOGY.md](ONTOLOGY.md).

---

## Remaining work, in recommended order

2. **Complete the top-50 editorial pass:** descriptions, icons, and the most important transitions.
   **Blocked on a display gap, found live 8 September 2026:** `icon` is not rendered anywhere in
   `/explore` (grepped `web/*.js` — zero references), so writing icons for the top 50 would be
   invisible work until a display location is designed. `short_adult_en` descriptions already
   render (the detail panel's main description paragraph falls back to it), but `short_child_en`
   has no display surface either — the adult/child reading-level toggle mentioned in STATUS.md
   phase 8 lived in the old `/` timeline (retired 31 August 2026) and was never ported to
   `/explore`. Needs a small design pass (where does an icon show? do we restore a child-level
   toggle, or drop `short_child_en` from this item's scope?) before continuing the content work.
3. **Add the linked map** — a geographic map view within `/explore`, linked to timeline navigation.
   No map code exists in `web/` yet (confirmed live 8 September 2026). Own spec, separate from
   item 3b below (split 8 September 2026 -- different output format, purpose, and audience).
3b. **Printable large-format visualization** (formerly item 8; merged into item 3 then split back
   out 8 September 2026 once it was clear the two are independent projects). STATUS.md phase 7
   ("Print poster") sketches an A1/A0 SVG renderer + PDF export, but no print code exists yet.
   Idea to explore: encode relative size/prominence (population, territory, or prominence_score)
   as band width or scale, closer to the original 1931 "Histomap of World History" poster's visual
   language (the app's namesake) than the current uniform-width bands. See
   `docs/superpowers/specs/` once a design exists.
4. **Work the Wikidata type-eligibility (622) and entity-type classification (2,709) backlogs.**
   Counts refreshed live 8 September 2026, re-running `pipeline/backfill_entity_types.py`'s exact
   `classify_entity`/`classify_automated_entity` logic read-only (no files written) rather than
   trusting the frozen 655/2,677 figures from 1 September -- both went up slightly, expected given
   this session's ~300 new records. `/type-review` and `/subdivision-review`, the dedicated queue
   UIs, were removed 3 September 2026 (see STATUS.md); per-record classification still happens via
   `/explore`'s side panel ("Set entity type" / the raw-fields editor) instead of a batch queue.
   **The real finding:** of the 2,709 entity-type classification backlog, 2,588 (95%) are flagged
   `pending_subdivision` -- their inferred type is `subdivision`, but the classifier deliberately
   keeps their existing type until a parent polity is confirmed (see `backfill_entity_types.py`'s
   `pending_subdivision` gate), and there is currently no UI to confirm one (`/subdivision-review`
   is gone). This is NOT ordinary manual review -- it's structurally blocked pending either a new
   parent-polity-confirmation mechanism or a decision to accept the current type permanently for
   these records. The remaining ~121 pending
   entity-type records, and the 622 eligibility-review records, genuinely are a long tail of
   low-count, ambiguous/obscure types needing ordinary one-by-one manual review via `/explore`.
   **Constraint:** `prominence_score` ranks polities against each other (most-to-least prominent,
   scoped by region) for display purposes only — it must never be a signal for `entity_type` or
   `timeline_role` classification. Those decisions come from Wikidata type evidence and editorial
   judgment, not from how prominent or well-documented a record happens to be.
