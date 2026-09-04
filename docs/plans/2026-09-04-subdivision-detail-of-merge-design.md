# Subdivision → detail_of Merge (ROADMAP Task 0 bis) — Design and Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire `Polity.parent`/`Polity.subdivision_parent_status` — a second, older mechanism for
"this entity nests inside that one" that duplicates what `Polity.detail_of` (the September 1 merge)
already covers — in favor of `detail_of` everywhere, and add real validation to `detail_of` (it
currently has none at all) to replace what `parent`'s validation used to check.

**Architecture:** `parent` turns out to be used far more broadly than just `entity_type:
subdivision` — 84 records carry it, only 1 of which is actually typed as a subdivision, and 15
already carry *both* `parent` and `detail_of` (mostly pointing at the same target, direct evidence
of the duplication). A one-off migration copies every `parent` value into `detail_of` (keeping the
existing `detail_of` value, dropping `parent`, when a record already has both). `entity_type:
subdivision` stays as a type label — it's still meaningful metadata, orthogonal to *where* an entity
nests, exactly like a phase-of entity keeps `entity_type: polity` while also having `detail_of` set.
`/explore` needs no changes for the common (single-level) case: `build_explore_tree.py` already
hides/nests purely off `detail_of` being set, regardless of `entity_type`.

**Multi-level chains are real data, not an error.** The dataset genuinely contains 3+-level
hierarchies (`Kingdom of Castile → Crown of Castile → Hispanic Monarchy`, 22 such chains found live
4 September 2026) — legitimate nested political structure, not a mistake to flatten away. This
migration preserves every existing chain exactly as-is; it does not flatten, reject, or otherwise
alter multi-level relationships already present in the data. What it does NOT do is make chains
*render* correctly: `build_explore_tree.py`'s current hide/nest logic only supports one level (an
entity whose `detail_of` target itself has `detail_of` set would leave that target hidden too, with
nothing rendering the chain's leaf under). That rendering gap is real, already guarded against
interactively (`/explore`'s "Set as detail of" picker already refuses a target that itself has
`detail_of` set, to avoid creating a *new* invisible chain), and is explicitly out of scope here —
see "Explicitly out of scope" below and the new ROADMAP item this plan's Task 5 adds.

**Tech Stack:** Python 3.12, Pydantic 2 (`schema.py`), PyYAML, `unittest` — matches every existing
plan in this directory. No new dependencies, no web/JS changes.

**Spec:** This document. The reasoning that produced it (a live-testing conversation surfacing the
duplication, a scan of the real dataset for `parent`'s true usage extent, and the chain-detection
check) lived in the brainstorming session that authored it.

## Global Constraints

- No new Python dependencies.
- `python -m unittest discover -s tests` must stay green after every task; `python build.py` must
  keep printing `OK` and its validated/written counts.
- The migration is one-off and non-destructive: every dropped `parent`/`subdivision_parent_status`
  value is preserved verbatim under `Polity.deprecated` (the same bucket the September 1 merge
  introduced), never deleted outright.
- `entity_type: subdivision` as a *type* is untouched in meaning — a subdivision is still a
  subdivision. Only the field that says *where it nests* (`parent` → `detail_of`) and the
  workflow-status field that gated its publication (`subdivision_parent_status`, already made moot
  by 3 September 2026's relaxation of `build.py`'s publish filter) go away.
- `save_entity_type()`'s existing `subdivision`-branch relationship-typing logic
  (`normalized_relationship_kind`/`relationship_kind`, the `administrative_part_of` relationship
  kind) is untouched — this plan only removes the `parent`/`subdivision_parent_status` field
  manipulation inside that branch, not the relationship-kind normalization machinery itself.

---

## Design summary

### 1. Schema (`schema.py`)

- Remove `Polity.parent: str | None = None` and `Polity.subdivision_parent_status:
  Literal["pending", "confirmed"] | None = None` entirely.
- Remove `_check()`'s validator branch that auto-defaults `subdivision_parent_status` to `"pending"`
  for subdivisions and rejects it for non-subdivisions (the whole field is gone, nothing to
  validate).
- Add real validation to `detail_of` (currently has none at all — not even "target must exist"):
  a new model validator rejects self-reference (`detail_of == self.id`) at the Pydantic level.
  "Target must exist" is deferred to a build-time check (`build.py`, Task 2 below), not a per-record
  Pydantic validator, since it needs the full dataset — matching how `parent`'s own cross-reference
  check already worked there. Chaining (a target that itself has `detail_of` set) is deliberately
  **not** rejected — multi-level nesting is real, legitimate data (see Architecture above); only
  `/explore`'s interactive picker guards against *creating* one, not the schema or build validation.

### 2. `build.py`

- Remove `validate_entity_relationships()`'s `parent`-specific branches (the "parent requires
  polity or subdivision → polity" check and the "confirmed subdivision requires a parent polity"
  check — both keyed off fields that no longer exist).
- Add one equivalent `detail_of` check in the same function: unknown target (`detail_of` points at
  an id not in the known set) — an error string in the same `errors: list[str]` this function
  already returns, matching its existing style exactly. No chaining check — multi-level `detail_of`
  chains are legitimate (see Architecture above), so a target that itself has `detail_of` set is not
  an error.

### 3. `server/app.py`

- `save_entity_type()`'s subdivision branch (`if entity_type == "subdivision": document["parent"] =
  None; document["subdivision_parent_status"] = "pending"` / `else: document.pop("subdivision_parent_status",
  None)`) is deleted outright — there is nothing left to reset. Setting or changing *any* polity's
  container — subdivision or not — happens through the existing `/explore` "Set as detail of"
  picker (`web/explore_details.js`, built 3 September 2026), which already writes `detail_of` via
  the generic `PATCH /api/polities/{id}/fields` endpoint. No new endpoint, no new UI.

### 4. One-off migration (`pipeline/migrate_parent_to_detail_of.py`)

One pass over `polities/*.yaml`, run once, each entity processed independently. Counted 4 September
2026: 84 records have `parent` set (83 `entity_type: polity`, 1 `entity_type: subdivision`); 15 of
those already also have `detail_of` set too. Re-run these counts before executing for real — more
may exist by then. No flattening, no chain detection — a chain (a `parent` target that itself has
`detail_of` set, or a `parent` target whose own `parent` will separately migrate to `detail_of` in
this same pass) is preserved exactly as multi-level data; see Architecture above for why.

For each polity with `parent` set:

- **If `detail_of` is already set** (the 15-record overlap): keep it as-is — it's the more
  deliberately-set field (from the September 1 merge or a later `/consolidation-review` decision) —
  and do not overwrite it with the `parent` value, even when they differ (e.g.
  `kingdom_of_the_algarve`: `parent` → the union kingdom, `detail_of` → Portugal specifically). Still
  record the original `parent` value under `deprecated["parent"]` for traceability, and append a
  one-line note to `notes` when the two values differ, naming both, so a human can spot a real
  discrepancy later if they want to.
- **If `detail_of` is not already set:** set `detail_of` to the `parent` value directly, unchanged.
- **Always**, regardless of the above: copy the *original* `parent` value into
  `deprecated["parent"]`, and `subdivision_parent_status` into
  `deprecated["subdivision_parent_status"]` if it was set. Remove `parent` and
  `subdivision_parent_status` from the document. `entity_type` is left exactly as it is (a
  subdivision stays a subdivision; a polity stays a polity) — this plan does not touch `entity_type`
  at all, only `parent`/`subdivision_parent_status`.

After the pass: `python build.py`, `pipeline.compute_prominence`, `pipeline.rebuild_timeline`, full
test suite.

### 5. Testing

- `tests/test_build.py`: `test_subdivision_requires_parent_polity` (exercises the retired
  `parent`-validation branches) is replaced with equivalent `detail_of` cases: unknown target is an
  error; a target that itself has `detail_of` set (a chain) is explicitly *not* an error; the
  baseline "no error when detail_of is absent or valid" case.
- New `tests/test_migrate_parent_to_detail_of.py`, mirroring `tests/test_migrate_detail_of.py`'s
  structure: a `parent`-only record migrates cleanly; a record with both `parent` and `detail_of`
  keeps `detail_of` and drops `parent` (with the `deprecated`/`notes` bookkeeping, including the
  differing-values case); a chained `parent` target (pointing at something that itself will get/has
  `detail_of`) migrates as-is, unflattened; an `independent`/untouched record (no `parent` at all)
  is left alone; a dry-run mode writes nothing.
- `schema.py`'s existing polity-validation tests gain a case confirming `detail_of == id` (self-
  reference) is rejected, and that `parent`/`subdivision_parent_status` are no longer accepted
  fields at all (extra-fields rejection, matching how the September 1 merge's own test suite
  confirmed `phase_of`/`part_of` were no longer accepted `consolidation_status` values).
- `tests/test_server.py`: any remaining reference to `parent`/`subdivision_parent_status` in
  `save_entity_type`'s tests (`test_accepts_subdivision_entity_type`) is trimmed to what's still
  true — setting `entity_type: subdivision` no longer touches any parent-related field at all.

---

## Explicitly out of scope

- Any change to `entity_type: subdivision` as a type value, or to how it's assigned (still via
  `PATCH /api/polities/{id}/entity-type`, unaffected by this plan).
- **N-level `/explore` rendering support.** `build_explore_tree.py`/`web/explore_timeline.js` only
  hide/nest one level today; a chain (already-existing or newly migrated) with 2+ links renders
  incorrectly (an intermediate link with its own `detail_of` set gets hidden too, orphaning
  whatever nests under it with no visible container). This plan deliberately does not fix that —
  it's a real, separate rendering design task, deferred the same way the original `detail_of`
  merge deferred its own `/explore` display half. Placed at the top of ROADMAP.md as its own item
  by this plan's Task 5. `/explore`'s "Set as detail of" picker already guards against
  *interactively creating* a new chain (refuses a target that itself has `detail_of` set) — that
  guard stays in place until the rendering gap closes, even though this migration itself preserves
  every chain already present in the data.
- Any change to the `administrative_part_of` relationship kind or `normalized_relationship_kind()` —
  only the `parent`/`subdivision_parent_status` *fields* retire, not the relationship-typing
  machinery around them.
- Retroactively resolving the discrepancy cases this migration surfaces but doesn't overwrite (e.g.
  `kingdom_of_the_algarve`) — they're logged, not adjudicated; that's ordinary editorial review, not
  part of this mechanical merge.

---

## Task 1: Schema — retire `parent`/`subdivision_parent_status`, validate `detail_of` self-reference

**Files:**
- Modify: `schema.py` (`Polity` class, `_check()` validator)
- Test: `tests/test_schema.py`

**Interfaces:**
- Produces: `Polity` with no `parent`/`subdivision_parent_status` fields; a `detail_of` that
  rejects self-reference at the Pydantic level (cross-record checks — unknown target, chaining —
  belong to Task 2's `build.py` work, not here).

- [ ] **Step 1: Write the failing tests**

In `tests/test_schema.py`, alongside the existing `PolityDetailOfTests` class (added by the
September 1 merge — reuse its `polity_kwargs` helper):

```python
class PolityParentRetirementTests(unittest.TestCase):
    def test_parent_field_no_longer_accepted(self) -> None:
        with self.assertRaises(ValidationError):
            Polity(**polity_kwargs(parent="spain"))

    def test_subdivision_parent_status_field_no_longer_accepted(self) -> None:
        with self.assertRaises(ValidationError):
            Polity(**polity_kwargs(subdivision_parent_status="pending"))

    def test_detail_of_rejects_self_reference(self) -> None:
        with self.assertRaises(ValidationError):
            Polity(**polity_kwargs(id="loop", detail_of="loop"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m unittest tests.test_schema -v`
Expected: the first two FAIL because Pydantic still accepts `parent`/`subdivision_parent_status` as
extra/known fields; the third FAILs because nothing currently rejects `detail_of == id`.

- [ ] **Step 3: Remove the fields and their validator branch**

In `schema.py`'s `Polity` class, remove the `parent: str | None = None` and
`subdivision_parent_status: Literal["pending", "confirmed"] | None = None` field declarations.

In `_check()`, remove the branch:

```python
        if self.entity_type == EntityType.subdivision:
            if self.subdivision_parent_status is None:
                self.subdivision_parent_status = "pending"
        elif self.subdivision_parent_status is not None:
            raise ValueError("subdivision_parent_status is only valid for subdivisions")
```

Add, in the same `_check()` method, a self-reference guard for `detail_of`:

```python
        if self.detail_of and self.detail_of == self.id:
            raise ValueError("detail_of cannot reference the entity's own id")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m unittest tests.test_schema -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `.venv/Scripts/python.exe -m unittest discover -s tests`
Expected: failures in `tests/test_build.py` (the retired `parent`-validation test) and possibly
`tests/test_server.py` — Tasks 2-3 below fix those. Confirm no *other* file breaks.

- [ ] **Step 6: Commit**

```bash
git add schema.py tests/test_schema.py
git commit -m "feat(schema): retire Polity.parent/subdivision_parent_status, validate detail_of self-reference"
```

---

## Task 2: `build.py` — replace parent validation with detail_of validation

**Files:**
- Modify: `build.py` (`validate_entity_relationships()`)
- Test: `tests/test_build.py`

**Interfaces:**
- Consumes: `Polity.detail_of` (already exists from the September 1 merge; Task 1 added the
  self-reference guard).
- Produces: `validate_entity_relationships()` reporting unknown-target and chaining errors for
  `detail_of`, in the same `errors: list[str]` shape it already returns for every other check.

- [ ] **Step 1: Write the failing tests**

Replace `test_subdivision_requires_parent_polity` in `tests/test_build.py` with:

```python
def detail_polity(polity_id: str, detail_of: str | None = None) -> Polity:
    return Polity.model_validate({
        "id": polity_id, "canonical_name": polity_id, "detail_of": detail_of,
        "start": 1, "end": 2, "start_confidence": "low", "end_confidence": "low",
    })


class DetailOfValidationTests(unittest.TestCase):
    def test_detail_of_unknown_target_is_reported(self) -> None:
        errors = validate_entity_relationships([detail_polity("child", "missing_parent")])
        self.assertIn("child: unknown detail_of target missing_parent", errors)

    def test_detail_of_chain_is_not_an_error(self) -> None:
        # Multi-level nesting is real, legitimate data (Kingdom of Castile
        # -> Crown of Castile -> Hispanic Monarchy, found live 4 September
        # 2026) -- only /explore's interactive picker guards against
        # creating a NEW one; build validation must not reject one already
        # in the data.
        grandparent = detail_polity("grandparent")
        middle = detail_polity("middle", "grandparent")
        child = detail_polity("child", "middle")
        self.assertEqual(validate_entity_relationships([grandparent, middle, child]), [])

    def test_detail_of_valid_target_has_no_error(self) -> None:
        parent = detail_polity("parent")
        child = detail_polity("child", "parent")
        self.assertEqual(validate_entity_relationships([parent, child]), [])
```

(Remove the now-obsolete `test_subdivision_requires_parent_polity` entirely — its two assertions
tested `parent`/`subdivision_parent_status`, both retired by Task 1.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m unittest tests.test_build -v`
Expected: FAIL — `validate_entity_relationships()` doesn't check `detail_of` at all yet.

- [ ] **Step 3: Remove the retired parent checks, add detail_of checks**

In `build.py`'s `validate_entity_relationships()`, remove the `if entity.parent:` /
`elif (entity.entity_type.value == "subdivision" and entity.subdivision_parent_status ==
"confirmed"):` branches entirely (both key off fields Task 1 removed from the schema). Add, in the
same function, right after the loop variable `known = {polity.id: polity for polity in polities}`
setup already at the top:

```python
    for entity in polities:
        if entity.detail_of and entity.detail_of not in known:
            errors.append(f"{entity.id}: unknown detail_of target {entity.detail_of}")
```

(Add this to the existing per-entity loop in the function, next to the other relationship checks.
Deliberately just the one check — no chaining rejection; see Architecture above.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m unittest tests.test_build -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `.venv/Scripts/python.exe -m unittest discover -s tests`
Expected: PASS (0 failures) — first point since Task 1 the whole suite should be green.

- [ ] **Step 6: Commit**

```bash
git add build.py tests/test_build.py
git commit -m "feat(build): replace parent's relationship validation with detail_of's (unknown target, no chaining)"
```

---

## Task 3: `server/app.py` — remove `save_entity_type()`'s subdivision field-reset

**Files:**
- Modify: `server/app.py` (`save_entity_type()`)
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `save_entity_type()` with no `parent`/`subdivision_parent_status` manipulation at all.

- [ ] **Step 1: Update the test**

`tests/test_server.py`'s `test_accepts_subdivision_entity_type` currently asserts
`saved["subdivision_parent_status"] == "pending"` after setting `entity_type: subdivision` — update
it to assert that field is simply absent:

```python
    def test_accepts_subdivision_entity_type(self) -> None:
        response = self.client.patch(
            "/api/polities/candidate/entity-type",
            json={"entity_type": "subdivision"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["entity_type"], "subdivision")
        saved = yaml.safe_load(
            (self.root / "polities" / "candidate.yaml").read_text(encoding="utf-8")
        )
        self.assertNotIn("subdivision_parent_status", saved)
        self.assertNotIn("parent", saved)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_server -v`
Expected: FAIL — `save_entity_type()` still sets `subdivision_parent_status: "pending"`.

- [ ] **Step 3: Remove the field-reset branch**

In `save_entity_type()`, remove:

```python
        if entity_type == "subdivision":
            document["parent"] = None
            document["subdivision_parent_status"] = "pending"
        else:
            document.pop("subdivision_parent_status", None)
```

(No replacement needed — there is nothing left to reset. If either `parent` or
`subdivision_parent_status` happens to still exist on a not-yet-migrated record, leave them
untouched here; Task 4's migration handles cleanup of existing data, this function just stops
*creating* new `subdivision_parent_status` values going forward.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m unittest tests.test_server -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python.exe -m unittest discover -s tests`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add server/app.py tests/test_server.py
git commit -m "feat(server): stop save_entity_type from touching parent/subdivision_parent_status"
```

---

## Task 4: One-off migration script

**Files:**
- Create: `pipeline/migrate_parent_to_detail_of.py`
- Test: `tests/test_migrate_parent_to_detail_of.py`

**Interfaces:**
- Consumes: `Polity.detail_of`/`Polity.deprecated` (existing); the `parent`/
  `subdivision_parent_status` values already in `polities/*.yaml` before this task runs.
- Produces: a `main(root: Path = ROOT, *, dry_run: bool = False) -> dict[str, int]` entry point
  returning `{"migrated": N, "kept_existing_detail_of": N}`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for pipeline/migrate_parent_to_detail_of.py -- the one-off
migration retiring Polity.parent/subdivision_parent_status in favor of the
already-existing Polity.detail_of field."""
import tempfile
import unittest
from pathlib import Path

import yaml

from pipeline.migrate_parent_to_detail_of import main


class MigrateParentToDetailOfTests(unittest.TestCase):
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

    def test_parent_only_record_migrates_to_detail_of(self) -> None:
        self.write_polity("realm_of_new_zealand", {"canonical_name": "Realm of New Zealand"})
        self.write_polity("new_zealand", {
            "canonical_name": "New Zealand", "entity_type": "subdivision",
            "subdivision_parent_status": "confirmed", "parent": "realm_of_new_zealand",
        })

        summary = main(self.root)

        self.assertEqual(summary["migrated"], 1)
        migrated = yaml.safe_load(
            (self.root / "polities" / "new_zealand.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(migrated["detail_of"], "realm_of_new_zealand")
        self.assertEqual(migrated["entity_type"], "subdivision")  # untouched by this migration
        self.assertNotIn("parent", migrated)
        self.assertNotIn("subdivision_parent_status", migrated)
        self.assertEqual(migrated["deprecated"]["parent"], "realm_of_new_zealand")
        self.assertEqual(migrated["deprecated"]["subdivision_parent_status"], "confirmed")

    def test_record_with_both_fields_keeps_existing_detail_of(self) -> None:
        self.write_polity("portugal", {"canonical_name": "Portugal"})
        self.write_polity("union_kingdom", {"canonical_name": "United Kingdom of Portugal, Brazil and the Algarves"})
        self.write_polity("kingdom_of_the_algarve", {
            "canonical_name": "Kingdom of the Algarve",
            "parent": "union_kingdom", "detail_of": "portugal",
            "notes": "Automatically generated from Wikidata; requires review.",
        })

        summary = main(self.root)

        self.assertEqual(summary["kept_existing_detail_of"], 1)
        migrated = yaml.safe_load(
            (self.root / "polities" / "kingdom_of_the_algarve.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(migrated["detail_of"], "portugal")
        self.assertNotIn("parent", migrated)
        self.assertEqual(migrated["deprecated"]["parent"], "union_kingdom")
        self.assertIn("union_kingdom", migrated["notes"])
        self.assertIn("portugal", migrated["notes"])

    def test_chained_parent_target_migrates_unflattened(self) -> None:
        # Multi-level nesting is legitimate data -- the migration preserves
        # it exactly, it does not flatten a chain to a single root.
        self.write_polity("syria", {"canonical_name": "Syria"})
        self.write_polity("french_mandate_for_syria_and_the_lebanon", {
            "canonical_name": "French Mandate for Syria and the Lebanon", "detail_of": "syria",
        })
        self.write_polity("french_mandate_of_lebanon", {
            "canonical_name": "French mandate of Lebanon",
            "parent": "french_mandate_for_syria_and_the_lebanon",
        })

        main(self.root)

        migrated = yaml.safe_load(
            (self.root / "polities" / "french_mandate_of_lebanon.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(migrated["detail_of"], "french_mandate_for_syria_and_the_lebanon")
        self.assertEqual(migrated["deprecated"]["parent"], "french_mandate_for_syria_and_the_lebanon")

    def test_records_without_parent_are_untouched(self) -> None:
        self.write_polity("sweden", {"canonical_name": "Sweden", "consolidation_status": "independent"})

        summary = main(self.root)

        self.assertEqual(summary["migrated"], 0)
        untouched = yaml.safe_load((self.root / "polities" / "sweden.yaml").read_text(encoding="utf-8"))
        self.assertEqual(untouched["consolidation_status"], "independent")
        self.assertNotIn("detail_of", untouched)

    def test_dry_run_writes_nothing(self) -> None:
        self.write_polity("realm_of_new_zealand", {"canonical_name": "Realm of New Zealand"})
        self.write_polity("new_zealand", {
            "canonical_name": "New Zealand", "entity_type": "subdivision",
            "parent": "realm_of_new_zealand",
        })

        summary = main(self.root, dry_run=True)

        self.assertEqual(summary["migrated"], 1)
        untouched = yaml.safe_load(
            (self.root / "polities" / "new_zealand.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(untouched["parent"], "realm_of_new_zealand")
        self.assertNotIn("detail_of", untouched)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_migrate_parent_to_detail_of -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.migrate_parent_to_detail_of'`

- [ ] **Step 3: Write the migration script**

```python
"""One-off migration: retire Polity.parent/subdivision_parent_status in
favor of the already-existing Polity.detail_of field -- a second, older
mechanism for "this entity nests inside that one" that turned out to
duplicate what detail_of (the September 1 merge) already covers. See
docs/plans/2026-09-04-subdivision-detail-of-merge-design.md.

Usage: python -m pipeline.migrate_parent_to_detail_of [--dry-run] [--root PATH]
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
    """Run the one-off parent/subdivision_parent_status -> detail_of
    migration. Returns a summary dict with migrated/kept_existing_detail_of
    counts. Does not flatten or otherwise alter multi-level chains -- a
    parent target that itself has (or will separately get) detail_of set
    is preserved exactly as multi-level data, not collapsed to one level.
    See docs/plans/2026-09-04-subdivision-detail-of-merge-design.md's
    Architecture section for why."""
    polities = _load_polities(root)
    summary = {"migrated": 0, "kept_existing_detail_of": 0}
    for polity_id, document in polities.items():
        old_parent = document.get("parent")
        if not old_parent:
            continue
        summary["migrated"] += 1

        deprecated = dict(document.get("deprecated") or {})
        deprecated["parent"] = old_parent
        if document.get("subdivision_parent_status"):
            deprecated["subdivision_parent_status"] = document["subdivision_parent_status"]

        if document.get("detail_of"):
            summary["kept_existing_detail_of"] += 1
            if document["detail_of"] != old_parent:
                note = (
                    f"Migration note (parent/detail_of merge, 4 September 2026): "
                    f"the retired parent field pointed at {old_parent}, kept detail_of "
                    f"({document['detail_of']}) as the deliberately-set value instead."
                )
                document["notes"] = (document.get("notes", "").rstrip() + " " + note).strip()
        else:
            document["detail_of"] = old_parent

        document["deprecated"] = deprecated
        document.pop("parent", None)
        document.pop("subdivision_parent_status", None)

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
    print(
        f"{'[dry run] ' if args.dry_run else ''}migrated {result['migrated']} records "
        f"({result['kept_existing_detail_of']} kept an existing detail_of)"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m unittest tests.test_migrate_parent_to_detail_of -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/migrate_parent_to_detail_of.py tests/test_migrate_parent_to_detail_of.py
git commit -m "feat(pipeline): add the one-off parent/subdivision_parent_status -> detail_of migration script"
```

---

## Task 5: Run the migration, rebuild, verify live, update docs, push

**Files:**
- Modify: `STATUS.md`, `ROADMAP.md` (mark task 0 bis done)

- [ ] **Step 1: Dry-run the migration against the real dataset**

Run: `.venv/Scripts/python.exe -m pipeline.migrate_parent_to_detail_of --dry-run`
Confirm the printed `migrated` count roughly matches `grep -cl "^parent:" polities/*.yaml` (84 as of
4 September 2026 — re-count first, more may exist by then).

- [ ] **Step 2: Run the migration for real**

Run: `.venv/Scripts/python.exe -m pipeline.migrate_parent_to_detail_of`

- [ ] **Step 3: Rebuild and recompute**

Run in order: `.venv/Scripts/python.exe build.py`, `.venv/Scripts/python.exe -m
pipeline.compute_prominence`, `.venv/Scripts/python.exe -m pipeline.rebuild_timeline`.

- [ ] **Step 4: Full test suite**

Run: `.venv/Scripts/python.exe -m unittest discover -s tests`
Expected: PASS

- [ ] **Step 5: Restart the server and verify live**

Find and kill the running server (`netstat -ano | grep ":8000"` / `taskkill //F //PID <pid>`),
restart (`.venv/Scripts/python.exe -m server.app`, backgrounded), poll
`curl http://127.0.0.1:8000/consolidation-review` until it responds 200. Verify via
`chrome-devtools`: navigate to `/explore?entity=new_zealand` (or another migrated single-level
record), confirm it's no longer an independent top-level band and instead appears as a detail chip
under its container when the container's toggle is opened; confirm zero console errors. Separately,
navigate to `/explore?entity=kingdom_of_castile` (a 3-level chain) and confirm the known, deferred
rendering gap actually reproduces as expected (the chain's leaf has no visible container to nest
under) — this is the documented, not-yet-fixed limitation Task 5's ROADMAP item covers, not a new
bug introduced by this migration.

- [ ] **Step 6: Update STATUS.md and ROADMAP.md**

`STATUS.md`: add a dated entry describing this merge (the true 84-record scope found vs. the
1-record subdivision case originally suspected, the 15 already-duplicated records, the 22 real
multi-level chains found and deliberately left unflattened, migration counts). `ROADMAP.md`: remove
task "0 bis" (this plan) from the list; add a new item **at the top of the list** for the deferred
N-level `/explore` rendering support this plan's Architecture and "Explicitly out of scope" sections
describe — `build_explore_tree.py`/`web/explore_timeline.js` only hide/nest one level of `detail_of`
today, so a chain's intermediate link gets hidden too, orphaning whatever nests under it; needs its
own design pass once this migration has landed and real multi-level chains exist as data to design
the renderer against (same "design against real data, not speculatively" precedent the original
`detail_of` merge's own deferred-display item followed).

- [ ] **Step 7: Commit and push**

```bash
git add polities/ data.json periods.json STATUS.md ROADMAP.md
git commit -m "data: migrate 84 parent records to detail_of, retiring the parent/subdivision_parent_status mechanism"
git push origin main
```

(Split into two commits if the migration diff and the docs update feel cleaner reviewed separately —
either is fine; this plan doesn't require a specific split here.)
