# Retire `visibility_tier`/`visibility_override` — Design + Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the `visibility_tier`/`visibility_override` concept entirely -- schema fields, the
`in_scope()` publish gate that reads them, every other place that reads or writes them, and the
`VisibilityTier` values already stored on ~4,663 of 4,697 `polities/*.yaml` records -- while
preserving the old values for audit under each record's `deprecated` bucket (the pattern Task 4 of
`docs/plans/2026-09-04-subdivision-detail-of-merge-design.md` established).

**Architecture:** `visibility_tier` was assigned by a now-retired competitive quota algorithm
(`compute_prominence.py`'s old `balanced_visibility()` pass; see `ONTOLOGY.md`'s "Ranking and
sizing" section) and has been frozen, unmaintained data ever since -- `compute_prominence.py`
explicitly does not touch it. `build_explore_tree.py`'s `in_scope()` check still uses it as a hard
publish gate, though: only 835 of 4,697 polities (~18%) currently render in `/explore`'s Polities
row, and because the field is frozen, a newly-added record can never earn its way into scope, only
be manually pinned one at a time via `visibility_override`. Removing the gate means every polity
becomes eligible to render; per direct instruction, nothing replaces it as a density-management
mechanism -- `detail_of` nesting (an entity that's a detail of another gets tucked into a
collapsed panel, not its own top-level band), zoom-to-narrow, and `weight_by_era` band width are
already the visual-density controls and stay the only ones.

**Tech Stack:** Python 3, Pydantic v2, PyYAML -- same as the rest of this repo. No new dependency.

**Spec:** This document. No separate spec file -- the design was presented and approved in chat
across three rounds (removal scope, density-management approach, and confirmation that old values
must survive under `deprecated`) before this doc was written, following this project's established
practice of folding the design into the same document as the plan.

## Global Constraints

- Every value migration preserves the old field values under `deprecated.visibility_tier` /
  `deprecated.visibility_override` rather than discarding them -- confirmed twice in review.
- `Polity` has no `model_config`/`extra=` override (confirmed in the 4 September 2026 merge), so it
  defaults to Pydantic v2's `extra="ignore"`: removing a field declaration makes an unknown kwarg on
  that field silently drop rather than raise. Tests asserting a retired field is gone must check
  field-absence (`hasattr`/`model_fields`), not an expected `ValidationError` -- the same fix
  already applied to the 4 September 2026 merge's schema tests.
- No new density-management/ranking mechanism is in scope for this pass -- `detail_of` nesting,
  zoom, and `weight_by_era` remain the only ones. Do not add a `prominence_score`-based cap
  "while we're at it."

## Design summary

1. **Schema (`schema.py`):** delete the `VisibilityTier` enum and the `Polity.visibility_tier` /
   `visibility_override` field declarations.
2. **Publish-gate removal:** delete `pipeline/suggest_period_links.py`'s `in_scope()` and its one
   call site; delete `pipeline/build_explore_tree.py`'s three `in_scope()` calls and the import.
   Every polity becomes eligible for period-link suggestions and for `/explore` rendering.
3. **`pipeline/review_cli.py`'s scoring:** the `tier` component (global=100/regional=50/detailed=0)
   is dropped from `review_priority()`'s composite score entirely, not replaced -- `candidate_impact`
   in the same formula already tracks current importance via the live `prominence_score`, while
   `tier` read frozen, no-longer-maintained data. `tier`'s freed 0.10 weight rolls entirely into
   `candidate_impact` (0.25 -> 0.35); every other weight is unchanged.
4. **Every remaining mechanical read/write site** (no behavioral decision left open -- see the
   per-file notes in Task 4): `pipeline/enrich_geography.py`'s by-tier reporting breakdown,
   `pipeline/period_hierarchy.py`'s `visibility_override`-pinned-first tiebreak in `top_entities()`
   (not wired into any live path today, only its own tests), `pipeline/apply_review_decisions.py`
   and `server/app.py`'s draft-record dicts (both were just spelling out the schema default; both
   also carry an already-dead `"parent": None` key left over from the 4 September 2026 merge,
   dropped opportunistically while touching these exact dicts), `web/explore_details.js`'s
   `Prominence: X / 100 (detailed)` display line (drops the parenthetical), and
   `pipeline/compute_prominence.py`'s now-stale "visibility_tier is not touched" docstring/print.
5. **Migration (`pipeline/migrate_visibility_tier.py`):** for every polity carrying
   `visibility_tier` and/or `visibility_override`, move both into
   `deprecated.visibility_tier`/`deprecated.visibility_override`, then strip the top-level keys.
   Mirrors `pipeline/migrate_parent_to_detail_of.py`'s exact shape (same helper functions, same
   `main(root, *, dry_run) -> dict[str, int]` signature).
6. **Run for real, rebuild, verify, document:** same closing sequence as Task 5 of the 4 September
   2026 merge plan.

## Explicitly out of scope

- **Any replacement ranking/capping mechanism for display density.** Confirmed directly: "show
  everything no cap, the detail_of is here to take care of this visual density." `top_entities()`
  stays unused by any live path (only its own tests exercise it) -- this pass fixes its
  `visibility_override` reference so it keeps working standalone, nothing more.
- **Task 0's multi-level `detail_of` rendering fix** (ROADMAP item 0). This pass removes the
  "walk past an invisible ancestor" complexity that task would otherwise have needed (13 of 31
  known chain leaves root at a now-formerly-invisible ancestor) -- once this ships, every
  `detail_of` root is by definition in scope, so task 0's own design simplifies to "recursive
  nesting only." Task 0 itself is unaffected and separate; sequencing was confirmed directly
  ("finish task 0 now, brainstorm visibility_tier removal next" was the original plan, reversed
  once this came up mid-brainstorm -- see STATUS.md for the full sequencing note).
- **`web/explore_details.js`'s dead `polity.parent` reference** (line 475, the "Part of" display
  row) -- already unreachable since the 4 September 2026 merge removed `Polity.parent` from the
  schema and its migration stripped it from every record, noticed while reading this exact file for
  an unrelated line, but a separate, pre-existing piece of dead code, not part of this task.

## Task 1: Schema — remove `VisibilityTier` and the two `Polity` fields

**Files:**
- Modify: `schema.py`
- Test: `tests/test_schema.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Polity` with no `visibility_tier`/`visibility_override` fields and no `VisibilityTier`
  export -- every later task's mechanical cleanup depends on these being gone.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_schema.py` (uses the existing `polity_kwargs()` helper already in that file):

```python
class VisibilityTierRetirementTests(unittest.TestCase):
    def test_visibility_tier_field_no_longer_accepted(self) -> None:
        polity = Polity(**polity_kwargs(visibility_tier="global"))
        self.assertFalse(hasattr(polity, "visibility_tier"))
        self.assertNotIn("visibility_tier", Polity.model_fields)

    def test_visibility_override_field_no_longer_accepted(self) -> None:
        polity = Polity(**polity_kwargs(visibility_override="global"))
        self.assertFalse(hasattr(polity, "visibility_override"))
        self.assertNotIn("visibility_override", Polity.model_fields)

    def test_visibility_tier_enum_no_longer_exported(self) -> None:
        import schema
        self.assertFalse(hasattr(schema, "VisibilityTier"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m unittest tests.test_schema -v`
Expected: FAIL -- `visibility_tier`/`visibility_override` are still real fields today (`hasattr`
returns `True`), and `schema.VisibilityTier` still exists.

- [ ] **Step 3: Remove the enum and the two fields**

In `schema.py`, delete:

```python
class VisibilityTier(str, Enum):
    global_ = "global"
    regional = "regional"
    detailed = "detailed"
```

and, from `Polity`:

```python
    visibility_tier: VisibilityTier = VisibilityTier.detailed
    visibility_override: VisibilityTier | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m unittest tests.test_schema -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `.venv/Scripts/python.exe -m unittest discover -s tests`
Expected: failures in every file that constructs a `Polity`/dict literal referencing
`visibility_tier`/`visibility_override` and asserts on it -- `tests/test_suggest_period_links.py`
(`InScopeTests`), `tests/test_build_explore_tree.py` (the `tier` param and `out_of_scope` test),
`tests/test_compute_prominence.py` (`ComputeDoesNotTouchVisibilityTierTests`),
`tests/test_period_hierarchy.py` (`test_visibility_override_is_pinned_first`), and
`tests/test_review_cli.py` (`test_priority_favors_globally_visible_prominent_candidates`'s `tier`
assertion). All fixed in Tasks 2-4. `Polity`'s `extra="ignore"` default means nothing raises here --
these tests fail on their own assertions, not on construction.

- [ ] **Step 6: Commit**

```bash
git add schema.py tests/test_schema.py
git commit -m "feat(schema): retire Polity.visibility_tier/visibility_override"
```

---

## Task 2: Remove the publish gate

**Files:**
- Modify: `pipeline/suggest_period_links.py`, `pipeline/build_explore_tree.py`
- Test: `tests/test_suggest_period_links.py`, `tests/test_build_explore_tree.py`

**Interfaces:**
- Consumes: Task 1's field removal (nothing in these two files constructs a `Polity` directly, both
  work on raw dicts, so this task doesn't strictly depend on Task 1 having landed -- but do it
  second regardless, so a partial implementation never has a schema that still validates the very
  field its gate keys off).
- Produces: `suggest_period_links.main()` and `build_explore_tree()` with no `in_scope`/scope
  concept at all -- every polity is eligible.

- [ ] **Step 1: Remove `in_scope()`'s tests**

In `tests/test_suggest_period_links.py`, delete the entire `InScopeTests` class (4 tests) and the
`in_scope` import (`from pipeline.suggest_period_links import best_period_for_polity, in_scope` ->
`from pipeline.suggest_period_links import best_period_for_polity`). `BestPeriodForPolityTests` is
untouched.

In `tests/test_build_explore_tree.py`:
- Drop the `tier: str = "global"` parameter and the `"visibility_tier": tier,` line from the
  `polity()` fixture helper.
- Delete the `polity("out_of_scope", -2500, -2400, "africa", "north_africa", tier="detailed")` line
  from `BuildExploreTreeTests.setUp`'s `self.polities` list.
- Delete the `test_out_of_scope_polity_excluded` test method entirely.

- [ ] **Step 2: Run tests to verify they fail (or error on the now-missing fixture)**

Run: `.venv/Scripts/python.exe -m unittest tests.test_suggest_period_links tests.test_build_explore_tree -v`
Expected: `test_suggest_period_links` fails to import (`in_scope` no longer exists once Step 3
below runs -- for now, with `in_scope` still present, this simply confirms the deleted tests are
gone and everything else still passes). `test_build_explore_tree` should already pass at this point
since removing an unused fixture line changes nothing about which tests exist.

- [ ] **Step 3: Remove `in_scope()` from `suggest_period_links.py`**

Delete:

```python
def in_scope(polity: dict) -> bool:
    if polity.get("visibility_override") == "global":
        return True
    return polity.get("visibility_tier") in {"global", "regional"}
```

In `main()`, change:

```python
    suggestions = []
    in_scope_count = 0
    unmatched = 0
    for path in sorted(POLITIES_DIR.glob("*.yaml")):
        polity = yaml.safe_load(path.read_text(encoding="utf-8"))
        if polity.get("timeline_role") == "period":
            continue
        if not in_scope(polity):
            continue
        in_scope_count += 1
        if polity["id"] in already_linked:
```

to:

```python
    suggestions = []
    candidates_seen = 0
    unmatched = 0
    for path in sorted(POLITIES_DIR.glob("*.yaml")):
        polity = yaml.safe_load(path.read_text(encoding="utf-8"))
        if polity.get("timeline_role") == "period":
            continue
        candidates_seen += 1
        if polity["id"] in already_linked:
```

(the `in_scope()` filter is gone; `candidates_seen` replaces `in_scope_count` one-for-one as a
plain `int` counter, so the "Already linked" derived count below still has a total to subtract
from):

```python
    SUMMARY_PATH.write_text(
        "# Polity to period-link suggestions\n\n"
        f"- Already linked: {candidates_seen - len(suggestions) - unmatched}\n"
        f"- Suggested: {len(suggestions)}\n"
        f"- Unmatched (no geography/date overlap with any period): {unmatched}\n",
        encoding="utf-8",
    )
    print(f"considered {candidates_seen}, suggested {len(suggestions)}, unmatched {unmatched}")
```

Update the module docstring's first sentence too: "suggest a
period_links.yaml entry for global/regional-tier polities that don't have one yet" -> "suggest a
period_links.yaml entry for polities that don't have one yet".

- [ ] **Step 4: Remove `in_scope()` calls from `build_explore_tree.py`**

Delete the import (`from pipeline.suggest_period_links import in_scope`) and simplify all three
call sites:

```python
        if polity.get("entity_type") not in CIVILIZATION_ENTITY_TYPES or not in_scope(polity):
```
becomes
```python
        if polity.get("entity_type") not in CIVILIZATION_ENTITY_TYPES:
```

```python
        if not target_id or not in_scope(polity):
```
becomes
```python
        if not target_id:
```

```python
            if not in_scope(polity):
                continue
```
is deleted outright (the `if` block's only statement).

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m unittest tests.test_suggest_period_links tests.test_build_explore_tree -v`
Expected: PASS

- [ ] **Step 6: Run the full test suite**

Run: `.venv/Scripts/python.exe -m unittest discover -s tests`
Expected: remaining failures only in `tests/test_compute_prominence.py`,
`tests/test_period_hierarchy.py`, and `tests/test_review_cli.py` (Task 4 and Task 3 respectively).

- [ ] **Step 7: Commit**

```bash
git add pipeline/suggest_period_links.py pipeline/build_explore_tree.py \
  tests/test_suggest_period_links.py tests/test_build_explore_tree.py
git commit -m "feat(pipeline): remove the visibility_tier publish gate -- every polity is now in scope"
```

---

## Task 3: `review_cli.py` — drop the `tier` scoring component

**Files:**
- Modify: `pipeline/review_cli.py`
- Test: `tests/test_review_cli.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `review_priority()` returning a `components` dict with no `"tier"` key, and a `score`
  computed from the renormalized weights below.

- [ ] **Step 1: Update the test**

Replace `test_priority_favors_globally_visible_prominent_candidates` with:

```python
    def test_priority_favors_prominent_candidates(self) -> None:
        record = {
            "start_year": 100,
            "end_year": 500,
            "peak_population_log10": 7,
            "peak_area_km2_log10": 6,
            "peak_social_complexity": 8,
            "candidates": [
                {"polity_id": "major", "total_score": 80},
                {"polity_id": "runner", "total_score": 78},
            ]
        }
        metadata = {
            "major": {
                "prominence_score": 75,
                "external_ids": {},
            }
        }
        high, components = review_priority(record, metadata)
        low, _ = review_priority(record, {})
        self.assertGreater(high, low)
        self.assertEqual(components["candidate_impact"], 75)
        self.assertNotIn("tier", components)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_review_cli -v`
Expected: FAIL -- `components` still has a `"tier"` key today.

- [ ] **Step 3: Remove the `tier` component, reweight**

In `review_priority()`, delete:

```python
    tier = {"global": 100.0, "regional": 50.0, "detailed": 0.0}.get(
        document.get("visibility_tier", "detailed"), 0.0
    )
```

and its use in the `components` dict (`"tier": tier,` line) and the fallback `components` dict for
the no-candidates early return (`"tier"` in that tuple of keys). Change the score formula from:

```python
    score = (
        0.30 * source_importance
        + 0.25 * candidate_impact
        + 0.20 * quality
        + 0.10 * ambiguity
        + 0.10 * tier
        + 0.05 * coverage
    )
```

to:

```python
    score = (
        0.30 * source_importance
        + 0.35 * candidate_impact
        + 0.20 * quality
        + 0.10 * ambiguity
        + 0.05 * coverage
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m unittest tests.test_review_cli -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `.venv/Scripts/python.exe -m unittest discover -s tests`
Expected: remaining failures only in `tests/test_compute_prominence.py` and
`tests/test_period_hierarchy.py` (Task 4).

- [ ] **Step 6: Commit**

```bash
git add pipeline/review_cli.py tests/test_review_cli.py
git commit -m "feat(pipeline): drop review_cli's tier scoring component, roll its weight into candidate_impact"
```

---

## Task 4: Every remaining mechanical read/write site

**Files:**
- Modify: `pipeline/enrich_geography.py`, `pipeline/period_hierarchy.py`,
  `pipeline/apply_review_decisions.py`, `server/app.py`, `web/explore_details.js`,
  `pipeline/compute_prominence.py`
- Test: `tests/test_period_hierarchy.py`, `tests/test_compute_prominence.py`

No behavioral decision is open in this task -- every change below either deletes a reporting
dimension for a field that no longer exists, or deletes a line that was just re-spelling the old
schema default.

- [ ] **Step 1: `pipeline/period_hierarchy.py` -- drop the pinning tiebreak**

Remove the test first. Delete `test_visibility_override_is_pinned_first` from
`tests/test_period_hierarchy.py`. Run `.venv/Scripts/python.exe -m unittest tests.test_period_hierarchy -v`
to confirm the remaining tests still pass (they will -- this file's other tests don't touch
`visibility_override`).

In `period_hierarchy.py`'s `top_entities()`, change:

```python
        def sort_key(entity_id: str) -> tuple[int, float, str]:
            polity = self._polities.get(entity_id, {})
            pinned = 0 if polity.get("visibility_override") else 1
            return (pinned, -polity.get("prominence_score", 0), entity_id)
```

to:

```python
        def sort_key(entity_id: str) -> tuple[float, str]:
            polity = self._polities.get(entity_id, {})
            return (-polity.get("prominence_score", 0), entity_id)
```

Update the module docstring's second sentence ("or reading the retired visibility_tier field,
itself") -- drop the `visibility_tier` clause since the field is now actually gone, not just
conceptually retired: "This is what a future timeline UI/API should import instead of re-deriving
broader_periods/period_links traversal itself."

- [ ] **Step 2: `pipeline/compute_prominence.py` -- drop the stale docstring/print**

Change the module docstring from:

```python
"""Compute auditable, type-aware prominence scores. Does not assign
visibility_tier -- that field is frozen; see ONTOLOGY.md's "Ranking and
sizing" section. Browsing/ranking uses pipeline/period_hierarchy.py's
top_entities() instead, scoped to whatever part of the tree is in view."""
```

to:

```python
"""Compute auditable, type-aware prominence scores. Browsing/ranking uses
pipeline/period_hierarchy.py's top_entities(), scoped to whatever part of
the tree is in view -- see ONTOLOGY.md's "Ranking and sizing" section."""
```

Delete the `by_tier` breakdown from `tests/test_compute_prominence.py`: remove the entire
`ComputeDoesNotTouchVisibilityTierTests` class (it tests a field that no longer exists). Then in
`compute_prominence.py` itself, change:

```python
    report_path.write_text(
        "# Prominence scores\n\n"
        f"- Records scored: {len(scores):,}\n"
        f"- Score range: {min(scores):.1f} - {max(scores):.1f}\n"
        f"- Mean score: {sum(scores) / len(scores):.1f}\n\n"
        "visibility_tier is not touched by this script -- it was frozen when the "
        "competitive balanced_visibility() pass was retired (see ONTOLOGY.md,\n"
        "'Ranking and sizing'). Browsing/ranking now uses "
        "pipeline/period_hierarchy.py's top_entities() instead.\n",
        encoding="utf-8",
    )
```

to:

```python
    report_path.write_text(
        "# Prominence scores\n\n"
        f"- Records scored: {len(scores):,}\n"
        f"- Score range: {min(scores):.1f} - {max(scores):.1f}\n"
        f"- Mean score: {sum(scores) / len(scores):.1f}\n",
        encoding="utf-8",
    )
```

and simplify the closing print:

```python
    print(f"Scored {result['scored']} records (visibility_tier untouched)")
```
to
```python
    print(f"Scored {result['scored']} records")
```

(also update `pipeline/rebuild_timeline.py`'s matching print of the same message.)

- [ ] **Step 3: `pipeline/enrich_geography.py` -- drop the by-tier report breakdown**

Delete the two `by_tier.setdefault(tier, ...)` lines and their preceding `tier = document.get(
"visibility_tier", "detailed")` lines (one in the `field_locked`/`only_missing` early-continue
branch, one after a fresh geography write), the `by_tier: dict[str, dict[str, int]] = {}`
declaration, and the report-writing loop:

```python
    for tier, values in sorted(by_tier.items()):
        lines.extend(["", f"## {tier.title()}", ""])
        lines.extend(f"- {key.replace('_', ' ').title()}: {value:,}" for key, value in values.items())
```

The report keeps its "## Overall" section (the `counts` dict), just loses the per-tier breakdown
sections beneath it.

- [ ] **Step 4: `pipeline/apply_review_decisions.py` and `server/app.py` -- drop dead draft keys**

In `apply_review_decisions.py`'s `draft` dict, delete both `"parent": None,` and
`"visibility_tier": "detailed",`.

In `server/app.py`'s period-promotion `entity` dict (the `else:` branch building a fresh polity
from a period), delete both `"parent": None,` and `"visibility_tier": "detailed",`.

- [ ] **Step 5: `web/explore_details.js` -- drop the tier label from the Prominence line**

Change:

```javascript
      <dt>Prominence</dt><dd>${Number(polity.prominence_score || 0).toFixed(2)} / 100 (${escapeHtml(polity.visibility_tier || "detailed")})</dd>
```

to:

```javascript
      <dt>Prominence</dt><dd>${Number(polity.prominence_score || 0).toFixed(2)} / 100</dd>
```

- [ ] **Step 6: Run the full test suite**

Run: `.venv/Scripts/python.exe -m unittest discover -s tests`
Expected: PASS (0 failures) -- first fully green point since Task 1.

- [ ] **Step 7: Commit**

```bash
git add pipeline/period_hierarchy.py pipeline/compute_prominence.py pipeline/rebuild_timeline.py \
  pipeline/enrich_geography.py pipeline/apply_review_decisions.py server/app.py \
  web/explore_details.js tests/test_period_hierarchy.py tests/test_compute_prominence.py
git commit -m "chore: remove every remaining visibility_tier/visibility_override read and write site"
```

---

## Task 5: One-off migration script

**Files:**
- Create: `pipeline/migrate_visibility_tier.py`
- Test: `tests/test_migrate_visibility_tier.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (works on raw YAML dicts, same as
  `migrate_parent_to_detail_of.py`).
- Produces: `main(root: Path = ROOT, *, dry_run: bool = False) -> dict[str, int]` returning
  `{"migrated": N}`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for pipeline/migrate_visibility_tier.py -- the one-off migration
retiring Polity.visibility_tier/visibility_override, preserving old values
under deprecated."""
import tempfile
import unittest
from pathlib import Path

import yaml

from pipeline.migrate_visibility_tier import main


class MigrateVisibilityTierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "polities").mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_polity(self, polity_id: str, fields: dict) -> None:
        (self.root / "polities" / f"{polity_id}.yaml").write_text(
            yaml.safe_dump({"id": polity_id, **fields}, sort_keys=False), encoding="utf-8"
        )

    def test_tier_only_record_moves_to_deprecated(self) -> None:
        self.write_polity("sweden", {"canonical_name": "Sweden", "visibility_tier": "regional"})

        summary = main(self.root)

        self.assertEqual(summary["migrated"], 1)
        migrated = yaml.safe_load(
            (self.root / "polities" / "sweden.yaml").read_text(encoding="utf-8")
        )
        self.assertNotIn("visibility_tier", migrated)
        self.assertEqual(migrated["deprecated"]["visibility_tier"], "regional")

    def test_tier_and_override_both_move_to_deprecated(self) -> None:
        self.write_polity("nazi_germany", {
            "canonical_name": "Nazi Germany",
            "visibility_tier": "detailed", "visibility_override": "global",
        })

        main(self.root)

        migrated = yaml.safe_load(
            (self.root / "polities" / "nazi_germany.yaml").read_text(encoding="utf-8")
        )
        self.assertNotIn("visibility_tier", migrated)
        self.assertNotIn("visibility_override", migrated)
        self.assertEqual(migrated["deprecated"]["visibility_tier"], "detailed")
        self.assertEqual(migrated["deprecated"]["visibility_override"], "global")

    def test_existing_deprecated_bucket_is_preserved_and_extended(self) -> None:
        self.write_polity("crown_of_castile", {
            "canonical_name": "Crown of Castile",
            "visibility_tier": "global",
            "deprecated": {"parent": "hispanic_monarchy"},
        })

        main(self.root)

        migrated = yaml.safe_load(
            (self.root / "polities" / "crown_of_castile.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(migrated["deprecated"]["parent"], "hispanic_monarchy")
        self.assertEqual(migrated["deprecated"]["visibility_tier"], "global")

    def test_records_without_either_field_are_untouched(self) -> None:
        self.write_polity("no_tier", {"canonical_name": "No Tier", "consolidation_status": "independent"})

        summary = main(self.root)

        self.assertEqual(summary["migrated"], 0)
        untouched = yaml.safe_load((self.root / "polities" / "no_tier.yaml").read_text(encoding="utf-8"))
        self.assertEqual(untouched["consolidation_status"], "independent")
        self.assertNotIn("deprecated", untouched)

    def test_dry_run_writes_nothing(self) -> None:
        self.write_polity("sweden", {"canonical_name": "Sweden", "visibility_tier": "regional"})

        summary = main(self.root, dry_run=True)

        self.assertEqual(summary["migrated"], 1)
        untouched = yaml.safe_load(
            (self.root / "polities" / "sweden.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(untouched["visibility_tier"], "regional")
        self.assertNotIn("deprecated", untouched)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m unittest tests.test_migrate_visibility_tier -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.migrate_visibility_tier'`

- [ ] **Step 3: Write the migration script**

```python
"""One-off migration: retire Polity.visibility_tier/visibility_override,
preserving old values under deprecated for audit. See
docs/plans/2026-09-05-retire-visibility-tier-design.md.

Usage: python -m pipeline.migrate_visibility_tier [--dry-run] [--root PATH]
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_polities(root: Path) -> dict[str, dict[str, Any]]:
    return {
        path.stem: yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for path in sorted((root / "polities").glob("*.yaml"))
    }


def main(root: Path = ROOT, *, dry_run: bool = False) -> dict[str, int]:
    """Run the one-off visibility_tier/visibility_override -> deprecated
    migration. Returns a summary dict with a migrated count."""
    polities = _load_polities(root)
    summary = {"migrated": 0}
    for polity_id, document in polities.items():
        has_tier = "visibility_tier" in document
        has_override = "visibility_override" in document
        if not has_tier and not has_override:
            continue
        summary["migrated"] += 1

        deprecated = dict(document.get("deprecated") or {})
        if has_tier:
            deprecated["visibility_tier"] = document.pop("visibility_tier")
        if has_override:
            deprecated["visibility_override"] = document.pop("visibility_override")
        document["deprecated"] = deprecated

        if not dry_run:
            (root / "polities" / f"{polity_id}.yaml").write_text(
                yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = main(args.root, dry_run=args.dry_run)
    print(f"{'[dry run] ' if args.dry_run else ''}migrated {result['migrated']} records")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m unittest tests.test_migrate_visibility_tier -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `.venv/Scripts/python.exe -m unittest discover -s tests`
Expected: PASS (0 failures)

- [ ] **Step 6: Commit**

```bash
git add pipeline/migrate_visibility_tier.py tests/test_migrate_visibility_tier.py
git commit -m "feat(pipeline): add the one-off visibility_tier/visibility_override -> deprecated migration script"
```

---

## Task 6: Run the migration, rebuild, verify live, update docs, push

**Files:**
- Modify: `STATUS.md`, `ROADMAP.md`

- [ ] **Step 1: Dry-run against the real dataset**

Run: `.venv/Scripts/python.exe -m pipeline.migrate_visibility_tier --dry-run`
Confirm the printed count roughly matches a fresh count of `polities/*.yaml` files carrying either
key (4,663 as of 4 September 2026's count-adjacent audit -- re-count first, since real editorial
activity happens continuously against this dataset).

- [ ] **Step 2: Run the migration for real**

Run: `.venv/Scripts/python.exe -m pipeline.migrate_visibility_tier`

Before committing, `git status` broadly and separate this migration's own file changes from any
unrelated concurrent live-UI edits already sitting in the working tree (a known, recurring
condition on this dataset -- stage and commit only the files this migration actually touched, never
`git add -A`).

- [ ] **Step 3: Rebuild and recompute**

Run in order: `.venv/Scripts/python.exe build.py`, `.venv/Scripts/python.exe -m
pipeline.compute_prominence`, `.venv/Scripts/python.exe -m pipeline.rebuild_timeline`.

- [ ] **Step 4: Full test suite**

Run: `.venv/Scripts/python.exe -m unittest discover -s tests`
Expected: PASS (0 failures)

- [ ] **Step 5: Verify live**

Restart the dev server (kill whatever holds port 8000, `python -m server.app` in the background)
and confirm: `/explore`'s Polities row now renders far more than 835 entries (spot check a
previously-`detailed`-tier record, e.g. one of the 13 Castile-cluster leaves from the 4 September
chain audit, now actually appears); the side panel's Prominence line no longer shows a tier
parenthetical; `/consolidation-review` still loads (its priority ordering now excludes the `tier`
component per Task 3).

- [ ] **Step 6: Update STATUS.md and ROADMAP.md**

Add a dated STATUS.md entry summarizing all 6 tasks (mirroring the detail level of the 4 September
2026 subdivision/detail_of merge entry). Re-read ROADMAP.md fresh before editing (it changes
independent of this work); update item 0 (multi-level `detail_of` rendering) to note the
"invisible ancestor" complexity it previously needed no longer applies, since every `detail_of`
root is now unconditionally in scope.

- [ ] **Step 7: Commit and push**

Stage exactly the polity files the migration modified plus the two docs -- never a blanket
`polities/*.yaml` glob, which would also sweep up any unrelated concurrent live-UI edits sitting in
the working tree (Step 2's warning). Cross-check the file count against the migration's own
printed/dry-run count before committing:

```bash
git status --short polities/ | wc -l   # cross-check against the migration's printed count
git add <the exact files the migration touched> STATUS.md ROADMAP.md
git commit -m "feat(data): run the visibility_tier -> deprecated migration for real"
git push origin main
```
