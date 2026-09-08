# Printable poster visualization -- design

ROADMAP.md item 3b (split from the former "linked map + printable visualization" line,
8 September 2026 -- the map is a separate, later project). Brainstormed live across several
sessions on 8 September 2026 via an iterated HTML/SVG mockup (published as the "Rivers of
Prominence" artifact), starting from the user's reference to the actual 1931 *Histomap of
World History* poster. User approved "implement that please" directly from the in-chat
mockup, the same lightweight path used for the Events lane -- this doc is a record of the
agreed design, not a separate approval-seeking artifact.

## Output

A static SVG file, generated on demand and downloaded -- not a new interactive on-screen
view (STATUS.md's original "print/render.py" sketch, still the right call: ships value
sooner, and the visual design needs to be validated on paper before an interactive version
is worth building). PDF export is out of scope for v1 (STATUS.md Phase 7's "PDF via headless
Chromium or paged.js" stays a later increment).

## Generation UX

One new page, `/poster`, with exactly three inputs and nothing else:

- **Style**: "Histomap Authentic" or "100% Stacked" (see below).
- **Start year** / **End year**: the printed window.
- **Generate** button -- triggers a download of `poster.svg`.

No column count, palette, or dimension controls in v1. `GET /api/poster.svg?style=...&start=...&end=...`
does the rendering server-side; the page is a thin form over that endpoint.

## The two styles

Both share the same layout skeleton (below); they differ only in how a polity's width is
computed.

- **Histomap Authentic** (mockup "Style A"): each *lineage* (a connected chain of polities --
  see "Lineages" below) gets its own fixed-ish column. A polity's width comes straight from
  `widthPx(prominence_score)`, independent of every other lineage. Columns don't compete for
  space; angular (not smoothed) edges with a small deterministic jitter, echoing the 1931
  original's hand-drawn irregularity.
- **100% Stacked** (mockup "Style A2"): the actual 1931 mechanic. At every sampled year,
  every active polity's width is its share of total prominence among everything active that
  year, and all active polities together always fill the canvas edge-to-edge -- nothing is
  ever independent of its neighbors. Requires the pan-in/pan-out mechanism below to avoid
  sharp snaps whenever a polity joins or leaves the shared pool.

Same vintage palette, same angular jittered path style, same gutter lanes in both -- only the
stacking math differs.

## Pan-in / pan-out (the taper mechanism)

One mechanism, used everywhere a polity's width needs to ease toward zero at its edges,
replacing two things that used to be unrelated in the mockup's first draft: a hand-placed
"declining to zero" keyframe, and a separate automatic pool-boundary smoothing formula only
Style A2 had.

- Every polity has an effective `fade_in_years` / `fade_out_years` (both default **15**).
  New optional Polity fields (schema.py) let a curator hand-author a longer one for a
  genuinely gradual historical decline (a slow multi-decade collapse) instead of a short
  boundary-smoothing taper. Nothing sets these explicitly at first; the default covers every
  existing record.
- The fade window straddles the boundary date rather than ending on it: `2/3 * duration`
  years before the date through `1/3 * duration` after -- confirmed timing, so the official
  date sits inside the ramp, not at either edge.
- No special-casing for successor hand-offs. Every polity uses the identical mechanism at its
  start and end, whether or not `transitions.json` connects it to a neighbor. For a *matched*
  hand-off (a `Transition` with matching prominence on both sides), fading both sides with
  the same window is mathematically invisible -- one side's rise exactly cancels the other's
  fall at every instant, since smoothstep is point-symmetric (`f(1-t) = 1-f(t)`). For a
  mismatched one (a split whose combined successors outweigh the parent), the same math gives
  a smooth ramp instead of a flat line -- correct, since that's a real change, not an
  artifact of the transition. This is why `Transition` data (currently only 5 curated
  records, see below) matters for the Stacked style specifically: it's what turns two
  otherwise-independent polities' default fades into a synchronized crossfade instead of two
  separately-timed tapers.
- A polity whose end is only the requested year-range's display cutoff (not a real historical
  end) never fades out at that edge -- it's still going, the poster just doesn't extend that
  far.

## Layout skeleton (vertical; time flows top-to-bottom)

Corrects one thing the mockup got wrong by using an invented, deliberately simplified
example: **not every context tier is global.** `Period` and `regional_era`-tier records are
region-specific by design (ONTOLOGY.md's whole point with `historical_regions`) -- there is
no single "the Era right now" value across every lineage simultaneously, the way the mockup's
toy dataset implied. Only `epoch_lane` periods and `macro_chapter`-tier periods are genuinely
global (`macro_chapter`'s own doc comment: "global macro-chapter backbone").

- **Right-hand gutter**, three narrow lanes with rotated labels (not four -- Era/Period
  dropped from the gutter for the reason above):
  - **Epoch** -- `epoch_lane` periods.
  - **Chapter** -- `macro_chapter`-tier periods.
  - **Events** -- tick marks from `events.json` (`eligibility: accepted` only, same as
    `/explore`); full labels stay in the left year-margin, not crammed into the lane.
- **Civilization / region context**: instead of the mockup's single global "Era" lane, each
  lineage's column carries its own light background wash from its `primary_historical_region`
  (or its civilization-lane period, where `detail_of`/`broader_periods` link one) -- more
  correct for a region-aware dataset than a fictional shared timeline would be.
- **Lineages**: the organic-flowing-band content. A lineage is a connected component of the
  selected polities under `successors` and `detail_of` edges (the same relationship data the
  consolidation queue and Transition model already use) -- not a hand-assigned group. Column
  left-to-right order: by the lineage's earliest polity's `start` year.
- **Polities**: top **60** by `prominence_score` (fixed for v1; not user-configurable) among
  polities overlapping `[start_year, end_year]`, each an organic flowing band per the chosen
  style.

## What's deliberately out of scope for v1

- The "linked map" item (separate ROADMAP line, separate project).
- PDF export -- SVG only.
- Column count / palette / dimension controls in the generation UI.
- A real fix for `transitions.json`'s sparse coverage (5 curated records) -- the Stacked
  style's crossfades will mostly fall back to independent (non-synchronized) fades until more
  Transitions are authored, same caveat already on ROADMAP item 2.

## Files

- `schema.py`: `Polity.fade_in_years: int | None`, `Polity.fade_out_years: int | None`.
- `pipeline/poster.py`: lineage grouping, the shared taper/stacking math, SVG string
  building. Pure functions, unit-testable without a server.
- `server/app.py`: `GET /api/poster.svg?style=authentic|stacked&start=<year>&end=<year>`.
- `web/poster.html` + `web/poster.js`: the three-input form.
- `tests/test_poster.py`.
