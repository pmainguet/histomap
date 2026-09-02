# Detail-of Merge (ROADMAP Task 0) — Design and Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **This plan covers Tasks 1-4 only** — the data-model merge (schema, backend decision handling, the one-off migration, the consolidation-review UI collapse). The `/explore` display half of ROADMAP task 0 (hiding detail entities by default, revealing them via a badge/zoom-triggered enclosing panel) is deliberately deferred to its own follow-up design pass — see "Deferred: `/explore` display" at the end of this document for why.

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

## Deferred: `/explore` display

Section 4 of the Design summary above (badge, enclosing panel, zoom-triggered auto-expand) is not
implemented by the tasks below. `web/explore_timeline.js`'s row rendering turned out deeper than the
brainstorming pass accounted for: three genuinely separate grouping-mode layout/draw function pairs
(`continentGroupedLayout`/`drawContinentGroupedRow`, `geoCountryGroupedLayout`/
`drawGeoCountryGroupedRow`, `flatLaneLayout`/`drawFlatLaneRow`), each computing its own row height
upfront from a flat item list, with no existing concept of per-item expand state or inline nested
rendering anywhere in the file. Reworking that cleanly across all three modes — consistent height
reflow, badge placement, zoom-triggered auto-open, collapse-on-zoom-away — needs its own focused
design pass once Tasks 1-4 below have landed and `detail_of` exists as real data to design the
renderer against, rather than being speculatively bolted onto this plan. `pipeline/build_explore_tree.py`
(Task 1-4 output already gives it what it needs: `Polity.detail_of`) is a reasonable Task 5 starting
point when that follow-up design happens: group `detail_of` entities by target at tree-build time so
the renderer isn't relearning the relationship from a flat list itself.

Until that follow-up ships, `/explore` renders migrated detail entities exactly like any other
polity — an independent top-level band in the Polities row, positioned by its own date+geography
like today. Not the target end state, but not a regression either: today every `phase_of`-derived
entity is invisible already (it doesn't exist as a Polity at all), and every `part_of`-derived
subdivision already renders as an independent top-level band — Tasks 1-4 below make detail entities
visible and correctly linked (via the "Part of" panel row), which is strictly more information than
today, just not yet hidden-by-default.

---

## Task 1: Schema — `detail_of` and `deprecated` fields

**Files:**
- Modify: `schema.py:162-256` (`Polity` class)
- Test: `tests/test_schema.py`

**Interfaces:**
- Produces: `Polity.detail_of: str | None`, `Polity.deprecated: dict[str, Any] | None` — read by
  every later task in this plan.

- [ ] **Step 1: Write the failing tests**

`tests/test_schema.py` today only tests `Period` (via its own `period_kwargs(**overrides)` helper,
`tests/test_schema.py:6-17`) — there is no existing `Polity` test or fixture in this file. Add a
matching `polity_kwargs` helper and a new test class, following the same style:

```python
from pydantic import ValidationError

from schema import Period, Polity


def polity_kwargs(**overrides: object) -> dict:
    value = {
        "id": "test_polity",
        "canonical_name": "Test Polity",
        "start": 1000,
        "start_confidence": "low",
        "end_confidence": "low",
    }
    value.update(overrides)
    return value


class PolityDetailOfTests(unittest.TestCase):
    def test_polity_accepts_detail_of_and_deprecated(self) -> None:
        polity = Polity(**polity_kwargs(
            detail_of="spain",
            deprecated={
                "consolidation_status": "phase_of",
                "consolidated_into": "spain",
                "period": {"id": "francoist_spain_period", "kind": "historical"},
            },
        ))
        self.assertEqual(polity.detail_of, "spain")
        self.assertEqual(polity.deprecated["consolidation_status"], "phase_of")

    def test_polity_rejects_retired_consolidation_status_values(self) -> None:
        with self.assertRaises(ValidationError):
            Polity(**polity_kwargs(consolidation_status="phase_of"))
        with self.assertRaises(ValidationError):
            Polity(**polity_kwargs(consolidation_status="part_of"))

    def test_polity_same_entity_still_requires_consolidated_into(self) -> None:
        with self.assertRaises(ValidationError):
            Polity(**polity_kwargs(consolidation_status="same_entity"))
```

(Add the `from pydantic import ValidationError` and `Polity` import to `tests/test_schema.py`'s
existing `from schema import Period` line at the top of the file — becomes `from schema import
Period, Polity` — rather than a second import line.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m unittest tests.test_schema -v`
Expected: `test_polity_accepts_detail_of_and_deprecated` fails with `ValidationError: Extra inputs
are not permitted` (or similar) for `detail_of`/`deprecated`; `test_polity_rejects_retired_consolidation_status_values`
fails because `"phase_of"`/`"part_of"` are still accepted today.

- [ ] **Step 3: Add the fields and narrow the Literal**

In `schema.py`, inside `class Polity(BaseModel):` (around `schema.py:173-176`):

```python
    consolidation_status: Literal["independent", "same_entity", "discarded"] | None = None
    consolidated_into: str | None = None
    detail_of: str | None = None
    deprecated: dict[str, Any] | None = None
    relationships: list[EntityRelationship] = Field(default_factory=list)
    parent: str | None = None
```

(This replaces the existing `consolidation_status: Literal["independent", "same_entity", "phase_of",
"part_of", "discarded"] | None = None` line at `schema.py:173`, dropping `"phase_of"`/`"part_of"`
and adding `detail_of`/`deprecated` right after `consolidated_into`.) Confirm `Any` is already
imported at the top of `schema.py` (it's a very common typing import; add `from typing import Any`
to the existing `typing` import line if it isn't there yet).

Update `_check()`'s validator (`schema.py:242-243`):

```python
        if self.consolidation_status == "same_entity" and not self.consolidated_into:
            raise ValueError("a consolidated entity requires consolidated_into")
```

(Drops `"phase_of"` from the `in {...}` check — `same_entity` is now the only value in that set, so
this simplifies to a plain `==`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m unittest tests.test_schema -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite and build**

Run: `.venv/Scripts/python.exe -m unittest discover -s tests` — expect failures in
`tests/test_consolidation_suggestions.py` and `tests/test_server.py` (they still assert the old
`phase_of`/`part_of` decision strings) — Task 2 below fixes those. Confirm the *only* new failures
are in those two files, nothing else, before continuing.

- [ ] **Step 6: Commit**

```bash
git add schema.py tests/test_schema.py
git commit -m "feat(schema): add Polity.detail_of and Polity.deprecated, retire phase_of/part_of from consolidation_status"
```

---

## Task 2: Backend — collapse decision handling to `detail_of`/`candidate_detail_of`

**Files:**
- Modify: `server/app.py:102-107` (`ConsolidationDecision`)
- Modify: `server/app.py:1173-1262` (`save_consolidation`)
- Modify: `server/app.py:1545-1606` (`decide_consolidation_review` dispatcher)
- Modify: `server/app.py` — `consolidation_review_queue()`'s `active` filter and `suggested_decision`
  assignment (the priority chain covered by `tests/test_consolidation_suggestions.py`)
- Modify: `tests/test_consolidation_suggestions.py` (every `phase_of`/`part_of`/`candidate_phase_of`/
  `candidate_part_of` expectation)
- Modify: `tests/test_server.py:220-281` (the three consolidation save/queue tests)

**Interfaces:**
- Consumes: `Polity.detail_of`/`Polity.deprecated` from Task 1.
- Produces: `save_consolidation()` accepting `decision in {"detail_of", "candidate_detail_of",
  "independent", "same_entity", "discarded"}` — consumed by Task 4's frontend.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_server.py:267-280`'s `test_converts_entity_phase_to_period_linked_to_target`
with:

```python
    def test_marks_entity_as_detail_of_target_without_creating_a_period(self) -> None:
        response = self.client.post(
            "/api/consolidation-reviews/candidate",
            json={"decision": "detail_of", "target_id": "container"},
        )

        self.assertEqual(response.status_code, 200)
        saved = yaml.safe_load((self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8"))
        self.assertEqual(saved["timeline_role"], "entity")
        self.assertEqual(saved["detail_of"], "container")
        self.assertNotIn("consolidation_status", saved)
        self.assertFalse((self.root / "periods" / "candidate_period.yaml").exists())

    def test_candidate_detail_of_marks_the_candidate_not_the_reviewed_entity(self) -> None:
        response = self.client.post(
            "/api/consolidation-reviews/candidate",
            json={"decision": "candidate_detail_of", "target_id": "container"},
        )

        self.assertEqual(response.status_code, 200)
        candidate_saved = yaml.safe_load((self.root / "polities" / "container.yaml").read_text(encoding="utf-8"))
        self.assertEqual(candidate_saved["detail_of"], "candidate")
        reviewed_saved = yaml.safe_load((self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8"))
        self.assertEqual(reviewed_saved["consolidation_status"], "independent")
```

(Match `test_keeps_consolidation_candidate_independent`'s existing `self.client`/fixture setup
pattern immediately above these — same `TestClient`, same pre-seeded `candidate.yaml`/`container.yaml`
fixtures already used by the tests being replaced.)

In `tests/test_consolidation_suggestions.py`, every `self.assertEqual(self.suggestion_for(...),
"phase_of")` becomes `"detail_of"`, every `"candidate_phase_of"` becomes `"candidate_detail_of"`,
every `"part_of"` becomes `"detail_of"`, every `"candidate_part_of"` becomes `"candidate_detail_of"`.
(`part_of` and `phase_of` both collapse into the same `detail_of` string now — direction, not
mechanism, is what the suggested-decision string still needs to communicate.) No fixture data
changes — every existing test's signals (naming pattern, dates, geography, documented relationships)
stay exactly as they are; only the expected output string changes.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m unittest tests.test_server tests.test_consolidation_suggestions -v`
Expected: FAIL — `decide_consolidation_review` still only accepts the old decision strings (422 on
`"detail_of"`/`"candidate_detail_of"`), and `suggested_decision` still returns `"phase_of"`/`"part_of"`.

- [ ] **Step 3: Collapse `ConsolidationDecision`**

`server/app.py:102-107`:

```python
class ConsolidationDecision(BaseModel):
    decision: Literal[
        "independent", "same_entity", "detail_of",
        "candidate_detail_of", "period", "discarded",
    ]
    target_id: str | None = None
```

- [ ] **Step 4: Rewrite `save_consolidation()`'s phase_of/part_of branch as one `detail_of` branch**

`server/app.py:1173-1262` — replace the `if decision == "independent": ... elif decision ==
"discarded": ... [rest of function]` structure's final `else:` branch (`server/app.py:1240-1256`,
the one that calls `write_period_record`/`append_period_link`) entirely. The new function:

```python
    def save_consolidation(entity_id: str, decision: str, target_id: str | None) -> dict:
        document = metadata.get(entity_id)
        if not document or document.get("timeline_role") == "retired" or document.get("consolidation_status") or document.get("detail_of"):
            raise HTTPException(404, "Consolidation review is not pending")
        if decision == "independent":
            document["consolidation_status"] = "independent"
            document["manual_overrides"] = sorted(set(document.get("manual_overrides", [])) | {"consolidation"})
            (polities_dir / f"{entity_id}.yaml").write_text(
                yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            metadata[entity_id] = document
            return document
        if decision == "discarded":
            document["timeline_role"] = "retired"
            document["eligibility"] = "excluded"
            document["consolidation_status"] = "discarded"
            document["manual_overrides"] = sorted(
                set(document.get("manual_overrides", [])) | {"consolidation", "eligibility"}
            )
            document["notes"] = (
                document.get("notes", "").rstrip()
                + " Editorially discarded as outside Histomap scope."
            ).strip()
            (polities_dir / f"{entity_id}.yaml").write_text(
                yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            metadata[entity_id] = document
            return document
        if decision == "same_entity":
            target = metadata.get(target_id or "")
            if not target or target_id == entity_id or target.get("timeline_role") == "retired":
                raise HTTPException(422, "target_id must identify another active entity")
            document["timeline_role"] = "retired"
            document["consolidation_status"] = "same_entity"
            document["consolidated_into"] = target_id
            document["manual_overrides"] = sorted(set(document.get("manual_overrides", [])) | {"consolidation"})
            aliases = {
                item.strip()
                for item in str((target.get("names") or {}).get("aliases_en", "")).split("|")
                if item.strip()
            }
            aliases.add(document["canonical_name"])
            target.setdefault("names", {})["aliases_en"] = " | ".join(sorted(aliases))
            target["sources"] = sorted(set(target.get("sources", [])) | set(document.get("sources", [])))
            target["manual_overrides"] = sorted(set(target.get("manual_overrides", [])) | {"consolidation"})
            (polities_dir / f"{target_id}.yaml").write_text(
                yaml.safe_dump(target, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            (polities_dir / f"{entity_id}.yaml").write_text(
                yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            metadata[entity_id] = document
            metadata[target_id] = target
            return document
        if decision == "detail_of":
            target = metadata.get(target_id or "")
            if not target or target_id == entity_id or target.get("timeline_role") == "retired":
                raise HTTPException(422, "target_id must identify another active entity")
            # No finite-end requirement and no Period record -- a detail
            # entity stays a live Polity with its own start/end, same as
            # before the decision. Replaces the old phase_of (which
            # manufactured a Period and retired the entity) and part_of
            # (which retyped entity_type to subdivision) mechanisms; see
            # docs/plans/2026-09-01-detail-of-merge-design.md.
            document["detail_of"] = target_id
            document["manual_overrides"] = sorted(set(document.get("manual_overrides", [])) | {"consolidation"})
            (polities_dir / f"{entity_id}.yaml").write_text(
                yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            metadata[entity_id] = document
            return document
        raise HTTPException(422, f"Unsupported consolidation decision: {decision}")
```

(`write_period_record`/`append_period_link` are no longer called from this function at all — they
stay defined and still used by `save_timeline_role()`'s unrelated `period`/`both` path, per this
plan's Global Constraints.)

- [ ] **Step 5: Update the dispatcher**

`server/app.py:1545-1606`, `decide_consolidation_review()` — replace every `"candidate_phase_of"`/
`"candidate_part_of"` branch with one `"candidate_detail_of"` branch, and the plain `"part_of"`
branch (`server/app.py:1586-1600`, which called `save_entity_type`/`save_subdivision_parent`) is
deleted outright — `"detail_of"` now falls through to the final `document = save_consolidation(...)`
call at the bottom, same as `"independent"`/`"same_entity"`/`"discarded"` already do:

```python
    @application.post("/api/consolidation-reviews/{entity_id}")
    async def decide_consolidation_review(entity_id: str, request: ConsolidationDecision) -> dict:
        refresh_period_role_queue()
        period_record = next((item for item in period_role_queue if item["id"] == entity_id), None)
        if request.decision == "candidate_detail_of":
            candidate_id = request.target_id or ""
            candidate = metadata.get(candidate_id)
            reviewed = metadata.get(entity_id)
            if not candidate or not reviewed or candidate_id == entity_id:
                raise HTTPException(422, "target_id must identify another active entity")
            save_consolidation(candidate_id, "detail_of", entity_id)
            if period_record is not None:
                save_timeline_role(entity_id, "entity", period_record.get("period_kinds", []))
            save_consolidation(entity_id, "independent", None)
            return {
                "status": "saved", "entity_id": entity_id,
                "decision": request.decision, "target_id": candidate_id,
            }
        if request.decision == "period":
            result = save_timeline_role(
                entity_id,
                request.decision,
                period_record.get("period_kinds", []) if period_record else [],
            )
            return {
                "status": "saved", "entity_id": entity_id, "decision": request.decision,
                "target_id": None, "period_id": result["period_id"],
            }
        if request.decision == "independent" and period_record is not None:
            save_timeline_role(entity_id, "entity", period_record.get("period_kinds", []))
        document = save_consolidation(entity_id, request.decision, request.target_id)
        return {
            "status": "saved", "entity_id": entity_id,
            "decision": request.decision, "target_id": document.get("consolidated_into") or document.get("detail_of"),
        }
```

- [ ] **Step 6: Collapse `suggested_decision`'s output values in `consolidation_review_queue()`**

Find every `suggested_decision = "phase_of"` and `suggested_decision = "part_of"` assignment and
change to `suggested_decision = "detail_of"`; every `suggested_decision = "candidate_phase_of"` and
`suggested_decision = "candidate_part_of"` to `suggested_decision = "candidate_detail_of"`. The
surrounding `if`/`elif` conditions (naming pattern, date containment, subdivision qualifier,
documented-relationship checks) are unchanged — this only touches the string each branch assigns.
Also update the `active` dict comprehension's filter to exclude entities with `detail_of` already
set:

```python
        active = {
            entity_id: document
            for entity_id, document in metadata.items()
            if document.get("timeline_role", "entity") not in {"retired", "period"}
            and document.get("eligibility") != "excluded"
            and not document.get("consolidation_status")
            and not document.get("detail_of")
        }
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m unittest tests.test_server tests.test_consolidation_suggestions -v`
Expected: PASS

- [ ] **Step 8: Run the full suite**

Run: `.venv/Scripts/python.exe -m unittest discover -s tests`
Expected: PASS (0 failures) — this is the first point where the whole suite should be green again
since Task 1's Step 5.

- [ ] **Step 9: Commit**

```bash
git add server/app.py tests/test_server.py tests/test_consolidation_suggestions.py
git commit -m "feat(server): collapse phase_of/part_of decision handling into detail_of/candidate_detail_of"
```

---

## Task 3: One-off migration script

**Files:**
- Create: `pipeline/migrate_detail_of.py`
- Test: `tests/test_migrate_detail_of.py`

**Interfaces:**
- Consumes: `Polity.detail_of`/`Polity.deprecated` from Task 1; the `consolidation_status:
  phase_of`/`consolidation_status: part_of` records already in `polities/*.yaml` before this task
  runs (168 and 6 respectively, counted 1 September 2026 — re-count with `grep -l
  "consolidation_status: phase_of" polities/*.yaml | wc -l` before running for real, since more may
  have been added since).
- Produces: a `main(root: Path, *, dry_run: bool = False) -> dict` entry point returning a summary
  (counts migrated, list of any records skipped with why) — dry_run prints what it would do without
  writing, for a safe first pass against the real dataset.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for pipeline/migrate_detail_of.py -- the one-off migration from
phase_of/part_of consolidation_status to the unified detail_of field."""
import tempfile
import unittest
from pathlib import Path

import yaml

from pipeline.migrate_detail_of import main


class MigrateDetailOfTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "polities").mkdir()
        (self.root / "periods").mkdir()
        (self.root / "period_links.yaml").write_text("[]\n", encoding="utf-8")
        (self.root / "period_links.json").write_text("[]", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_polity(self, polity_id: str, fields: dict) -> None:
        (self.root / "polities" / f"{polity_id}.yaml").write_text(
            yaml.safe_dump({"id": polity_id, **fields}, sort_keys=False), encoding="utf-8"
        )

    def test_migrates_phase_of_record_back_to_a_live_polity(self) -> None:
        self.write_polity("spain", {
            "canonical_name": "Spain", "start": 1516, "end": None,
            "start_confidence": "low", "end_confidence": "low",
        })
        self.write_polity("francoist_spain", {
            "canonical_name": "Francoist Spain", "start": 1939, "end": 1975,
            "start_confidence": "low", "end_confidence": "low",
            "timeline_role": "retired", "consolidation_status": "phase_of",
            "consolidated_into": "spain",
        })
        (self.root / "periods" / "francoist_spain_period.yaml").write_text(
            yaml.safe_dump({
                "id": "francoist_spain_period", "canonical_name": "Francoist Spain",
                "kind": "historical", "start": 1939, "end": 1975,
                "start_confidence": "low", "end_confidence": "low",
                "geography": {}, "broader_periods": [], "successors": [],
                "authority": "Histomap editorial consolidation",
                "external_ids": {}, "notes": "", "source_urls": [],
            }, sort_keys=False), encoding="utf-8",
        )
        (self.root / "period_links.yaml").write_text(yaml.safe_dump([
            {"period_id": "francoist_spain_period", "entity_id": "spain",
             "relation": "phase_of", "source_urls": [], "notes": ""},
        ]), encoding="utf-8")

        summary = main(self.root)

        self.assertEqual(summary["migrated_phase_of"], 1)
        migrated = yaml.safe_load(
            (self.root / "polities" / "francoist_spain.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(migrated["detail_of"], "spain")
        self.assertEqual(migrated["timeline_role"], "entity")
        self.assertNotIn("consolidation_status", migrated)
        self.assertNotIn("consolidated_into", migrated)
        self.assertEqual(migrated["deprecated"]["consolidation_status"], "phase_of")
        self.assertEqual(migrated["deprecated"]["consolidated_into"], "spain")
        self.assertEqual(migrated["deprecated"]["period"]["id"], "francoist_spain_period")
        self.assertEqual(migrated["deprecated"]["period_link"]["relation"], "phase_of")
        self.assertFalse((self.root / "periods" / "francoist_spain_period.yaml").exists())
        remaining_links = yaml.safe_load((self.root / "period_links.yaml").read_text(encoding="utf-8"))
        self.assertEqual(remaining_links, [])

    def test_migrates_part_of_record_and_reverts_entity_type(self) -> None:
        self.write_polity("realm_of_new_zealand", {
            "canonical_name": "Realm of New Zealand", "start": 1983, "end": None,
            "start_confidence": "low", "end_confidence": "low",
        })
        self.write_polity("new_zealand", {
            "canonical_name": "New Zealand", "start": 1841, "end": None,
            "start_confidence": "low", "end_confidence": "low",
            "entity_type": "subdivision", "subdivision_parent_status": "confirmed",
            "parent": "realm_of_new_zealand", "consolidation_status": "part_of",
        })

        summary = main(self.root)

        self.assertEqual(summary["migrated_part_of"], 1)
        migrated = yaml.safe_load(
            (self.root / "polities" / "new_zealand.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(migrated["detail_of"], "realm_of_new_zealand")
        self.assertEqual(migrated["entity_type"], "polity")
        self.assertNotIn("parent", migrated)
        self.assertNotIn("subdivision_parent_status", migrated)
        self.assertNotIn("consolidation_status", migrated)
        self.assertEqual(migrated["deprecated"]["parent"], "realm_of_new_zealand")
        self.assertEqual(migrated["deprecated"]["entity_type"], "subdivision")

    def test_leaves_independent_and_same_entity_records_untouched(self) -> None:
        self.write_polity("sweden", {
            "canonical_name": "Sweden", "start": 1523, "end": None,
            "start_confidence": "low", "end_confidence": "low",
            "consolidation_status": "independent",
        })

        summary = main(self.root)

        self.assertEqual(summary["migrated_phase_of"], 0)
        self.assertEqual(summary["migrated_part_of"], 0)
        untouched = yaml.safe_load((self.root / "polities" / "sweden.yaml").read_text(encoding="utf-8"))
        self.assertEqual(untouched["consolidation_status"], "independent")
        self.assertNotIn("detail_of", untouched)

    def test_dry_run_writes_nothing(self) -> None:
        self.write_polity("spain", {
            "canonical_name": "Spain", "start": 1516, "end": None,
            "start_confidence": "low", "end_confidence": "low",
        })
        self.write_polity("francoist_spain", {
            "canonical_name": "Francoist Spain", "start": 1939, "end": 1975,
            "start_confidence": "low", "end_confidence": "low",
            "timeline_role": "retired", "consolidation_status": "phase_of",
            "consolidated_into": "spain",
        })
        (self.root / "periods" / "francoist_spain_period.yaml").write_text(
            yaml.safe_dump({
                "id": "francoist_spain_period", "canonical_name": "Francoist Spain",
                "kind": "historical", "start": 1939, "end": 1975,
                "start_confidence": "low", "end_confidence": "low",
                "geography": {}, "broader_periods": [], "successors": [],
                "authority": "x", "external_ids": {}, "notes": "", "source_urls": [],
            }, sort_keys=False), encoding="utf-8",
        )

        summary = main(self.root, dry_run=True)

        self.assertEqual(summary["migrated_phase_of"], 1)
        untouched = yaml.safe_load(
            (self.root / "polities" / "francoist_spain.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(untouched["consolidation_status"], "phase_of")
        self.assertTrue((self.root / "periods" / "francoist_spain_period.yaml").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_migrate_detail_of -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.migrate_detail_of'`

- [ ] **Step 3: Write the migration script**

```python
"""One-off migration: retire the phase_of/part_of consolidation_status
mechanisms in favor of Polity.detail_of, preserving every old field value
under Polity.deprecated. See docs/plans/2026-09-01-detail-of-merge-design.md.

Usage: python -m pipeline.migrate_detail_of [--dry-run] [--root PATH]
"""
import argparse
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_polities(root: Path) -> dict[str, dict[str, Any]]:
    return {
        path.stem: yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for path in sorted((root / "polities").glob("*.yaml"))
    }


def _write_polity(root: Path, polity_id: str, document: dict[str, Any], *, dry_run: bool) -> None:
    if dry_run:
        return
    (root / "polities" / f"{polity_id}.yaml").write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def _migrate_phase_of(root: Path, polity_id: str, document: dict[str, Any], *, dry_run: bool) -> None:
    period_path = root / "periods" / f"{polity_id}_period.yaml"
    period = yaml.safe_load(period_path.read_text(encoding="utf-8")) if period_path.exists() else None

    links_path = root / "period_links.yaml"
    links = yaml.safe_load(links_path.read_text(encoding="utf-8")) or [] if links_path.exists() else []
    matching_link = next(
        (link for link in links if link.get("period_id") == f"{polity_id}_period"
         and link.get("relation") == "phase_of"),
        None,
    )
    remaining_links = [link for link in links if link is not matching_link]

    deprecated = dict(document.get("deprecated") or {})
    deprecated["consolidation_status"] = document.get("consolidation_status")
    deprecated["consolidated_into"] = document.get("consolidated_into")
    if period is not None:
        deprecated["period"] = period
    if matching_link is not None:
        deprecated["period_link"] = matching_link

    target_id = document.get("consolidated_into")
    document["detail_of"] = target_id
    document["deprecated"] = deprecated
    document.pop("consolidation_status", None)
    document.pop("consolidated_into", None)
    document["timeline_role"] = "entity"

    _write_polity(root, polity_id, document, dry_run=dry_run)
    if not dry_run:
        if period_path.exists():
            period_path.unlink()
        links_path.write_text(yaml.safe_dump(remaining_links, sort_keys=False), encoding="utf-8")
        json_path = root / "period_links.json"
        if json_path.exists():
            json_path.write_text(json.dumps(remaining_links), encoding="utf-8")


def _migrate_part_of(root: Path, polity_id: str, document: dict[str, Any], *, dry_run: bool) -> None:
    deprecated = dict(document.get("deprecated") or {})
    deprecated["consolidation_status"] = document.get("consolidation_status")
    deprecated["parent"] = document.get("parent")
    deprecated["subdivision_parent_status"] = document.get("subdivision_parent_status")
    deprecated["entity_type"] = document.get("entity_type")

    document["detail_of"] = document.get("parent")
    document["deprecated"] = deprecated
    document.pop("consolidation_status", None)
    document.pop("parent", None)
    document.pop("subdivision_parent_status", None)
    document["entity_type"] = "polity"

    _write_polity(root, polity_id, document, dry_run=dry_run)


def main(root: Path = ROOT, *, dry_run: bool = False) -> dict[str, int]:
    """Run the one-off phase_of/part_of -> detail_of migration. Returns a
    summary dict with migrated_phase_of/migrated_part_of counts."""
    polities = _load_polities(root)
    summary = {"migrated_phase_of": 0, "migrated_part_of": 0}
    for polity_id, document in polities.items():
        status = document.get("consolidation_status")
        if status == "phase_of":
            _migrate_phase_of(root, polity_id, document, dry_run=dry_run)
            summary["migrated_phase_of"] += 1
        elif status == "part_of":
            _migrate_part_of(root, polity_id, document, dry_run=dry_run)
            summary["migrated_part_of"] += 1
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = main(args.root, dry_run=args.dry_run)
    print(f"{'[dry run] ' if args.dry_run else ''}migrated {result['migrated_phase_of']} phase_of "
          f"and {result['migrated_part_of']} part_of records")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m unittest tests.test_migrate_detail_of -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/migrate_detail_of.py tests/test_migrate_detail_of.py
git commit -m "feat(pipeline): add the one-off phase_of/part_of -> detail_of migration script"
```

---

## Task 4: Consolidation-review UI — collapse to two buttons

**Files:**
- Modify: `web/consolidation_review.js:19-22` (shortcut key arrays)
- Modify: `web/consolidation_review.js:95-129` (`recommendableButton`, `candidateMarkup`)
- Modify: `web/consolidation_review.js` keydown handler (the `phaseKeys`/`partKeys`/
  `inversePhaseKeys`/`inversePartKeys` branches)

**Interfaces:**
- Consumes: `decide(decision, targetId)` (unchanged signature) now sends `"detail_of"`/
  `"candidate_detail_of"` instead of the four retired strings, matching Task 2's collapsed
  `ConsolidationDecision`.

- [ ] **Step 1: Collapse the shortcut key arrays**

`web/consolidation_review.js:19-22` — two arrays instead of four (AZERTY row layout unchanged in
spirit, just fewer keys needed now):

```javascript
const detailKeys = ["A", "Z", "E", "R", "T"];
const inverseDetailKeys = ["D", "F", "G", "H", "J"];
```

- [ ] **Step 2: Collapse the buttons in `candidateMarkup`**

`web/consolidation_review.js:125` — replace the four `recommendableButton` calls for phase/part
with two for `detail_of`/`candidate_detail_of`:

```javascript
      <div class="review-actions relationship-directions">${recommendableButton("same_entity", candidate, index + 1, "Same entity")}<button type="button" data-decision="independent"${independentRecommended ? ' class="recommended-decision"' : ""}><kbd>K</kbd> Independent entity</button>${recommendableButton("detail_of", candidate, detailKeys[index], "Reviewed → detail of candidate", reviewedOpenEnded ? "Reviewed entity is still open-ended (present)" : null)}${recommendableButton("candidate_detail_of", candidate, inverseDetailKeys[index], "Candidate → detail of reviewed", candidateOpenEnded ? "Candidate is still open-ended (present)" : null)}</div>
```

(`reviewedOpenEnded`/`candidateOpenEnded` and their `hint` text no longer mention end-date
approximation specifically, since `detail_of` never touches `end` at all now — only the "still
open-ended" fact remains worth a tooltip, not what happens to it.)

- [ ] **Step 3: Collapse the keydown handler**

The keydown handler currently has four consecutive `else if` branches for `phaseKeys`/
`inversePhaseKeys`/`partKeys`/`inversePartKeys` (right after the `digit`/`same_entity` branch, right
before the `"k"` independent-entity branch):

```javascript
  } else if (phaseKeys.includes(event.key.toUpperCase())) {
    const candidate = current.candidates[phaseKeys.indexOf(event.key.toUpperCase())];
    if (!candidate) return;
    event.preventDefault();
    decide("phase_of", candidate.id);
  } else if (inversePhaseKeys.includes(event.key.toUpperCase())) {
    const candidate = current.candidates[inversePhaseKeys.indexOf(event.key.toUpperCase())];
    if (!candidate) return;
    event.preventDefault();
    decide("candidate_phase_of", candidate.id);
  } else if (partKeys.includes(event.key.toUpperCase())) {
    const candidate = current.candidates[partKeys.indexOf(event.key.toUpperCase())];
    if (!candidate) return;
    event.preventDefault(); decide("part_of", candidate.id);
  } else if (inversePartKeys.includes(event.key.toUpperCase())) {
    const candidate = current.candidates[inversePartKeys.indexOf(event.key.toUpperCase())];
    if (!candidate) return;
    event.preventDefault(); decide("candidate_part_of", candidate.id);
```

Replace all four with two:

```javascript
  } else if (detailKeys.includes(event.key.toUpperCase())) {
    const candidate = current.candidates[detailKeys.indexOf(event.key.toUpperCase())];
    if (!candidate) return;
    event.preventDefault();
    decide("detail_of", candidate.id);
  } else if (inverseDetailKeys.includes(event.key.toUpperCase())) {
    const candidate = current.candidates[inverseDetailKeys.indexOf(event.key.toUpperCase())];
    if (!candidate) return;
    event.preventDefault();
    decide("candidate_detail_of", candidate.id);
```

- [ ] **Step 4: Manual verification (no JS test harness in this repo)**

Start the server (`$py -m server.app`), open `/consolidation-review`, confirm: exactly two
direction buttons render per candidate (not four), their keyboard shortcuts fire `detail_of`/
`candidate_detail_of` (check the Network tab's request body), and an open-ended entity's tooltip no
longer mentions end-date approximation.

- [ ] **Step 5: Commit**

```bash
git add web/consolidation_review.js
git commit -m "feat(web): collapse consolidation-review's four phase/part buttons into two detail_of buttons"
```

---

## Task 5: Run the migration, rebuild, verify live, update docs, push

**Files:**
- Modify: `STATUS.md`, `ROADMAP.md` (mark task 0's data-model half done; the display half stays
  open per this plan's "Deferred" section)

- [ ] **Step 1: Dry-run the migration against the real dataset**

Run: `.venv/Scripts/python.exe -m pipeline.migrate_detail_of --dry-run`
Confirm the printed counts roughly match `grep -l "consolidation_status: phase_of" polities/*.yaml |
wc -l` / `grep -l "consolidation_status: part_of" polities/*.yaml | wc -l` (168/6 as of 1 September
2026, but re-count first — more may have been added since).

- [ ] **Step 2: Run the migration for real**

Run: `.venv/Scripts/python.exe -m pipeline.migrate_detail_of`

- [ ] **Step 3: Rebuild and recompute**

Run in order: `.venv/Scripts/python.exe build.py`, `.venv/Scripts/python.exe -m
pipeline.compute_prominence`, `.venv/Scripts/python.exe -m pipeline.rebuild_timeline`.

- [ ] **Step 4: Full test suite**

Run: `.venv/Scripts/python.exe -m unittest discover -s tests`
Expected: PASS

- [ ] **Step 5: Restart the server and verify live**

Kill the running server PID (`netstat -ano | grep ":8000"` / `taskkill //F //PID <pid>`), restart
(`$py -m server.app`, `run_in_background: true`), poll `curl
http://127.0.0.1:8000/api/consolidation-reviews?limit=1` until it responds 200. Verify via
`chrome-devtools`: navigate to `/consolidation-review`, confirm two-button layout, zero console
errors; navigate to `/explore`, spot-check a couple of migrated records (e.g. `francoist_spain`)
appear as ordinary Polities-row bands (expected per this plan's "Deferred" section — not hidden yet)
and their side panel shows a correct "Part of" row pointing at `spain`.

- [ ] **Step 6: Update STATUS.md and ROADMAP.md**

`STATUS.md`: add a dated entry describing this merge (schema fields, decision collapse, migration
counts, and that `/explore` display remains a follow-up). `ROADMAP.md`: mark task 0's data-model
half complete, leave a note that the `/explore` hide/reveal half is still open, referencing this
plan's "Deferred" section for why and what a follow-up plan would need to cover.

- [ ] **Step 7: Commit and push**

```bash
git add polities/ periods/ period_links.yaml period_links.json data.json periods.json STATUS.md ROADMAP.md
git commit -m "data: migrate 168 phase_of and 6 part_of records to detail_of"
git push origin main
```

(Split into two commits if the migration diff and the docs update feel cleaner reviewed separately —
either is fine; this plan doesn't require a specific split here.)
