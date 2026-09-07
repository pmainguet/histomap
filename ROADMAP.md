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
5. Allow simple edit of the parent era for periods in /explore (dropdown)
6. When side panel open, pressing ESC key should close it.
7. put new entity and Build time line on the same line than "Explore human history" title, right align
8. Add with the buttons a search field to find entities and then on select, focus on the entity and open side panel
9. Polity dropdown should have options Show All, Show Main (the biggest one in terms of score so that only the most important ones), Hide
10. Check the missing elements appearing https://en.wikipedia.org/wiki/Human_history (like Axial Age), extract wikidata, wikipedia elements and adjust the score if needed (if above the threshold that's enough)
11. Display more pictures and information from wikipedia on the side panel (even read there instead of wikipedia if possible)
12. Extracft missing data from Histomap and History of Evolution map
13. Add a start / end year selector to zoom in/out
14. Brainstorm on how to have a nice visualization out of this dataset printable in big size
