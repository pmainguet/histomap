# Detail-of Merge (ROADMAP Task 0) — Design

**Goal:** Replace `phase_of`/`candidate_phase_of`/`part_of`/`candidate_part_of` — two structurally
different consolidation-review mechanisms that both mean "this entity is a detail of that one" —
with a single `detail_of` relationship, and make `/explore` hide detail entities by default,
revealing them only when their container is zoomed into or its badge is clicked.

**Architecture:** A new `Polity.detail_of: str | None` field replaces the semantic content of both
old mechanisms; a new `Polity.deprecated: dict[str, Any] | None` field preserves every old field
value under its original name so no history is lost. `phase_of` currently manufactures a synthetic
`Period` record and retires the polity (it vanishes from the published dataset); `part_of`
currently retypes the polity to `entity_type: subdivision` and sets `parent`. Both effects are
undone: a detail entity stays a live, published `Polity` — the same shape it already had — with one
pointer field saying what it's a detail of. `/explore`'s tree builder groups detail entities under
their container instead of placing them as independent top-level bands; the renderer reveals them
in an enclosing panel that becomes the container's own band expanded downward, either on a manual
badge click or automatically when the existing "Zoom to this" action targets that entity.

**Tech Stack:** Python 3.12, Pydantic 2 (`schema.py`), PyYAML, `unittest`; vanilla JS
(`web/explore_timeline.js`, `web/explore_details.js`, `web/consolidation_review.js`), no new
dependencies, no build step — matches every existing plan in this directory.

**Spec:** This document. No separate spec source; the reasoning that produced it (Q&A + an approved
visual mockup of the panel treatment) lived in the brainstorming session that authored it.

## Global Constraints

- No new Python or JS dependencies.
- `python -m unittest discover -s tests` must stay green after every task; `python build.py` must
  keep printing `OK` and its validated/written counts.
- The migration is one-off and non-destructive: every old field value for a migrated record is
  preserved verbatim under `deprecated`, never deleted outright. The generated `periods/*_period.yaml`
  files and their `period_links.yaml` rows for migrated `phase_of` records ARE deleted from their
  live locations (their content lives on in `deprecated` instead) — this is the one designed
  exception to "never delete," since the whole point is that a Period record was never the right
  shape for this relationship.
- `/subdivision-review`'s own workflow (`entity_type: subdivision`, `subdivision_parent_status`,
  `parent`) is untouched in meaning and behavior — this plan only removes the *coupling* where
  applying `part_of` via `/consolidation-review` used to also retype the entity, it does not change
  what `/subdivision-review` itself does for entities that are genuinely administrative subdivisions.
- `consolidation_status`/`consolidated_into` remain exactly as they are today for the
  `same_entity`/`independent`/`discarded` outcomes — this plan only retires their `"phase_of"`/
  `"part_of"` values in favor of `detail_of`.

---

## Design summary

### 1. Schema (`schema.py`)

- Add `detail_of: str | None = None` to `Polity` — the id of the entity this one is a detail of.
  Deliberately no `kind` discriminator (phase vs. part): the whole point of this merge is that the
  distinction no longer matters structurally. Both directions of a consolidation decision write
  this same field (on the reviewed entity for `detail_of`, on the candidate for `candidate_detail_of`).
- Add `deprecated: dict[str, Any] | None = None` to `Polity` — a generic, unstructured bucket for
  old field values under their original names. Not schema-validated beyond being a dict; it's a
  historical record, not live data anything reads back.
- `Polity.consolidation_status`'s `Literal` drops `"phase_of"` and `"part_of"`, keeping
  `"independent" | "same_entity" | "discarded"`.
- `_check()`'s validator (`schema.py:242-243`, "a consolidated entity requires consolidated_into")
  drops `"phase_of"` from its check, keeping it only for `"same_entity"`. No new validator ties
  `detail_of` to anything else — a detail entity keeps its own independent `start`/`end`/`geography`,
  same as any other polity; there's no structural requirement it be the same as its container's.

### 2. Backend decision handling (`server/app.py`)

- `ConsolidationDecision`'s accepted values collapse from `{phase_of, part_of, candidate_phase_of,
  candidate_part_of, independent, same_entity, discarded, period}` to `{detail_of,
  candidate_detail_of, independent, same_entity, discarded, period}` (`period` is the unrelated
  polity→period-reclassification queue's own decision — see Global Constraints — untouched).
- New save path (replacing today's `save_consolidation()` phase_of branch and the
  `save_entity_type()`+`save_subdivision_parent()` part_of branch): sets `document["detail_of"] =
  target_id`, `document["manual_overrides"] += {"consolidation"}`. No Period creation. No
  `entity_type` retyping. No `subdivision_parent_status` touch. The entity is never retired
  (`timeline_role` stays `"entity"`); it keeps existing as a normal, published `Polity`.
- `candidate_detail_of` mirrors today's `candidate_phase_of`/`candidate_part_of` handling: it's the
  same save path applied with reviewed/candidate swapped, not a second code path.
- `consolidation_review_queue()`'s existing signals (`regime_of_candidate`/`reviewed`,
  `subdivision_of_candidate_name`/`reviewed_name`, `date_contains`/`reverse_date_contains`,
  `reviewed_part_of_candidate`/`candidate_part_of_reviewed`, `documented_successor`, etc.) are
  unchanged — they already decide *whether* a relationship holds and *which direction*. Only the
  `suggested_decision` output values collapse: `phase_of`→`detail_of`,
  `candidate_phase_of`/`part_of`/`subdivision_part_of_candidate`→ still resolve toward whichever
  direction they already pointed, just labeled `detail_of`/`candidate_detail_of` instead of four
  separate strings. `same_entity`/`independent`/`None` are unaffected.
- Active-queue filtering (`active = {...}` in `consolidation_review_queue()`) gains `and not
  document.get("detail_of")` alongside its existing `not document.get("consolidation_status")` check,
  so a resolved detail entity leaves the queue the same way an `independent`/`same_entity` decision does.

### 3. One-off migration (`pipeline/migrate_detail_of.py`)

Two passes over `polities/*.yaml`, run once, each entity processed independently:

- **168 `consolidation_status: phase_of` records:** locate `periods/<id>_period.yaml` (deterministic
  name, `write_period_record()`'s own convention, `server/app.py:1119`) and its `period_links.yaml`
  row (`period_id == <id>_period`, `relation == "phase_of"`). Snapshot `{consolidation_status:
  "phase_of", consolidated_into: <target>, period: <full period dict>, period_link: <full row>}`
  into `deprecated`. Set `detail_of = <target>`. Remove `consolidation_status`/`consolidated_into`
  (now redundant with `deprecated`/`detail_of`). Restore `timeline_role: "entity"`. Leave
  `start`/`end`/`end_confidence` as they are (including any earlier open-ended-end approximation —
  it's real recorded data now, not reverted). Delete the `periods/<id>_period.yaml` file and its
  `period_links.yaml` row from their live locations.
- **6 `consolidation_status: part_of` records:** snapshot `{consolidation_status: "part_of", parent:
  <old value>, subdivision_parent_status: "confirmed", entity_type: "subdivision"}` into
  `deprecated`. Set `detail_of = <old parent value>`. Revert `entity_type` to `"polity"`. Clear
  `parent`/`subdivision_parent_status`.
- After both passes: `python build.py`, `pipeline.compute_prominence`, `pipeline.rebuild_timeline`,
  full test suite. Expect `data.json`'s published entity count to rise by up to 168 (previously
  Period-only entries becoming Polities again) minus however many still get excluded from the
  default view by the new tree-builder grouping (Section 4) — the entities exist in the dataset
  either way; only their *default visibility* in `/explore`'s top-level rows changes.

### 4. `/explore` display (`pipeline/build_explore_tree.py`, `web/explore_timeline.js`,
`web/explore_details.js`)

- Tree-build time: group every polity with `detail_of` set by its target id. A detail entity is
  excluded from the Polities row's normal per-chapter region/continent bucketing (never an
  independent top-level band); instead it's attached to its container's tree node as a `details:
  [...]` list.
- A container with one or more details gets a small count badge on its band. The container's band
  is otherwise drawn exactly as today.
- **Reveal = enclosing panel** (per the approved mockup): clicking the badge toggles that
  container's panel open. The container's own band becomes the panel's bordered header; its
  details render inside the same box below it, as a simple wrapped row of chips (not
  date-positioned sub-lanes — the mockup showed, and the approval confirmed, that detail entities
  don't need timeline-precise x/width inside the panel).
- **Reveal also triggers from zoom**: `web/explore_details.js`'s existing "Zoom to this" button
  (wired to `onZoomToRange`, `web/explore_details.js:413-418`) additionally opens that entity's own
  panel if it's a container, and opens its *container's* panel if the zoomed entity is itself a
  detail — directly implementing "only show details if we zoom on the entity itself." Zooming away
  from a container's range collapses its panel again.
- Multiple containers can be expanded independently; no artificial limit. Expand state is
  client-side only (a `Set` of expanded container ids in `explore_timeline.js`'s render state) and
  does not persist across reloads — resets to fully collapsed.
- Row height reflows as panels open/close, reusing the redraw path zoom already triggers
  (`web/explore_timeline.js`'s tree-to-SVG render, not a new mechanism).
- Detail panel (`web/explore_details.js`): `renderPolityDetails()`'s existing `parent`-based "Part
  of"/"Contains" rows (`web/explore_details.js:378`, `:364`) are re-pointed to read `detail_of`
  instead of `parent` — same UI, corrected source field. `renderPeriodDetails()`'s unlabeled
  "Linked entities" list loses its `phase_of`-period case entirely (no more Period records are
  created this way going forward; migrated ones no longer exist).

### 5. Consolidation-review UI (`web/consolidation_review.js`, `web/consolidation_review.html`)

- The four buttons (Reviewed→phase of candidate / Reviewed→part of candidate / Candidate→phase of
  reviewed / Candidate→part of reviewed) collapse to two: **Reviewed → detail of candidate** /
  **Candidate → detail of reviewed**. Keyboard shortcuts collapse correspondingly (frees up the
  AZERTY key rows the retired buttons used).
- "Why suggested" reasoning text keeps its existing granularity (still says *why* — regime-naming,
  subdivision-qualifier, documented relationship, date nesting — it just no longer needs to also
  announce which of two outcome buttons that evidence was for).

### 6. Testing

- `tests/test_consolidation_suggestions.py`: every existing `phase_of`/`part_of`/`candidate_phase_of`/
  `candidate_part_of` expectation becomes `detail_of`/`candidate_detail_of`. Signal-level assertions
  (which naming pattern fired, geography, dates) are unchanged.
- New `tests/test_detail_of_migration.py` (or a script-level test in the migration's own module):
  exercises the migration against a small synthetic fixture set covering both the phase_of and
  part_of shapes, asserting the exact `deprecated` snapshot shape and that `detail_of`/`entity_type`/
  `timeline_role` land correctly, and that no other record is touched.
- `schema.py`'s existing polity-validation test suite gains cases for `detail_of` +
  `deprecated`, and confirms the retired `phase_of`/`part_of` `consolidation_status` values are no
  longer accepted.
- Manual browser verification (this repo's established pattern for `web/*.js`, no JS test harness):
  badge click, zoom-triggered auto-expand, multi-container independent expand state, panel
  collapse-on-zoom-away, `/consolidation-review`'s two-button flow end to end.

---

## Explicitly out of scope

- Any change to `/subdivision-review`'s own review flow or the meaning of a *genuine* administrative
  subdivision — this plan only removes consolidation's incidental coupling to it.
- Persisting expand/collapse state across page reloads.
- Any change to the polity→period reclassification queue (`timeline_role: period`/`both`,
  `save_timeline_role()`) — a different, legitimate use of Period records untouched by this plan.
- Migrating/relabeling `deprecated` data further after this one-off pass; it's a permanent historical
  record, not a working field anything reads going forward.
