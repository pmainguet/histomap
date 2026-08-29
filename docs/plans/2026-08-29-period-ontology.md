# Period Ontology Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the dataset an explicit, curated chronological hierarchy (macro chapter → regional era → named period) that a future timeline UI can browse, scoped ranking (`top_entities`) that replaces the retired global competitive visibility-tier algorithm, and no leftover dead code implying the old algorithm is still authoritative.

**Architecture:** Extend the existing `Period` model rather than replace it. `periods/*.yaml` already has `broader_periods` (parent-chain) and `period_links.yaml` already links polities into periods — this plan adds two new tiers of `Period` records (`macro_chapter`, `regional_era`) sitting above the 117 existing periods, a build-time validator enforcing which tier can parent which, and a scope-local ranking helper. It also removes `compute_prominence.py`'s competitive `balanced_visibility()` quota algorithm outright (not just stops calling it) — see `ONTOLOGY.md`'s "Ranking and sizing" section for why freezing in place isn't enough.

**Tech Stack:** Python 3.12, Pydantic 2 (`schema.py`), PyYAML, `unittest` (project's existing test runner — not pytest).

**Spec:** [`ONTOLOGY.md`](../../ONTOLOGY.md) — the durable, living definition of the ontology this plan implements. This plan executes it once; `ONTOLOGY.md` stays authoritative afterward and should be updated first if the design changes.

## Global Constraints

- Do not delete or rename any existing field, YAML file, or id, **except** the functions named in Task 8 (`balanced_visibility`, `_top_per_stratum`, `visibility_stratum`, `historical_era`, `tier_for` in `pipeline/compute_prominence.py`) and their dedicated tests — those are a deliberate, scoped removal, not collateral damage.
- Every one of the 4,671 `polities/*.yaml` and 117 `periods/*.yaml` files must still validate unchanged after every task except Task 8, which changes what `compute_prominence.py` writes but is not required to run against the full dataset (see Task 8, Step 5).
- `python -m unittest discover -s tests` must stay green after every task (137 tests today).
- `python build.py` must keep printing `OK` and its validated/written counts after every task.
- No task hand-classifies more than ~25 records by hand. Anything larger becomes a heuristic-suggestion script + a reviewable report under `reports/`, following the existing pattern in `pipeline/classify_period_roles.py` and `pipeline/review_cli.py`.
- This plan stops at the data layer. It does not touch `web/` or `server/`, and does not build the Holocene/geological display layer (per `ONTOLOGY.md`, that's a static UI asset for the future timeline plan, not a `Period`-tree citizen).
- No documentary-status/evidence-basis fields anywhere — dropped after review (see `ONTOLOGY.md`'s "Why this exists").
- No `overlaps`/`associated_with` relationship schema, and no "parallel display lanes" data structure. Per `ONTOLOGY.md`'s "Tree, lanes, graph" section: the `Period` tree (this plan) answers "where am I in the curated account of history"; a future UI's parallel lanes answer "what else was true at the same time" by computing overlap from `start`/`end`/`geography` at render time — nothing to persist; and "how is this connected to that" is already answered by the existing `Polity.relationships` graph (`political_parent`, `cultural_component`, `associated_people`, ...), unchanged by this plan. All three are deliberately separate concerns; this plan only builds the first.

---

## Design summary

Full rationale lives in [`ONTOLOGY.md`](../../ONTOLOGY.md). Summary of what it means for the schema:

1. Chronological hierarchy = a chain of `Period` records using the already-existing `broader_periods` field, tagged by a new `tier: Literal["macro_chapter", "regional_era", "period"] = "period"` field. Every existing period file stays valid untouched under the default.
2. `broader_periods` holds **exactly one entry** for every period this plan authors (schema type stays `list[str]` for flexibility, but the convention is single-parent, enforced by Task 2's build-time validator). A parent pointer is editorial placement, not a date-range containment claim — periods may (and several do) run past their parent's boundary.
3. Entities keep linking into the hierarchy via the existing `period_links.yaml`, plus a new `relation: "defines"` value for the "this period exists specifically to give this polity a period-tier presence" case.
4. `Period.kind` is untouched and not deprecated — nothing in this plan replaces its evidentiary role.
5. `YEAR_MIN` moves from -10,000 to -3,000,000 so the Paleolithic macro chapter can express its real start date. This only widens the allowed range.
6. `compute_prominence.py`'s competitive `balanced_visibility()` quota algorithm is deleted (Task 8), not frozen. `prominence_score` computation stays. Scoped ranking moves to `pipeline/period_hierarchy.py`'s new `top_entities()`.
7. Only `tier: macro_chapter` may have `geography.continents: []`; everywhere else that means "unknown," never "global."

---

## File structure

- Modify: `schema.py` — `Period.tier`, `YEAR_MIN` change (Task 1)
- Create: `tests/test_schema.py` (Task 1)
- Modify: `build.py` — `validate_period_tiers()` (Task 2)
- Create: `tests/test_validate_period_tiers.py` (Task 2)
- Create: `periods/macro_*.yaml` × 9 (Task 3)
- Create: `pipeline/seed_regional_eras.py` — 20-row hand-curated table + writer (Task 4)
- Create: `pipeline/generate_modern_regional_eras.py` — data-driven continent×chapter generator for macro chapters 6-9 (Task 4)
- Create: `tests/test_seed_regional_eras.py`, `tests/test_generate_modern_regional_eras.py` (Task 4)
- Create: `periods/*_era.yaml` × 20 + however many the generator produces (Task 4 output)
- Create: `pipeline/suggest_regional_eras.py` + `tests/test_suggest_regional_eras.py` (Task 5)
- Create: `reports/regional_era_suggestions.jsonl`, `reports/regional_era_summary.md` (Task 5 output)
- Create: `pipeline/suggest_period_links.py` + `tests/test_suggest_period_links.py` (Task 6)
- Create: `reports/period_link_suggestions.jsonl`, `reports/period_link_suggestion_summary.md` (Task 6 output)
- Create: `pipeline/period_hierarchy.py` + `tests/test_period_hierarchy.py` (Task 7)
- Modify: `pipeline/compute_prominence.py`, `tests/test_compute_prominence.py` (Task 8)
- Modify: `schema.py` — `Geography.historical_regions`/`primary_historical_region` (Task 9)
- Create: `pipeline/historical_regions.py`, `pipeline/derive_historical_regions.py` + tests (Task 9)
- Create: `reports/historical_region_coverage.md` (Task 9 output)
- Modify: `Makefile`, `PLAN.md`, `README.md` (Task 10)

---

## Task 1: Schema foundations

**Files:**
- Modify: `schema.py`
- Create: `tests/test_schema.py`

**Interfaces:**
- Produces: `Period.tier: Literal["macro_chapter", "regional_era", "period"] = "period"`
- Produces: `YEAR_MIN = -3_000_000` (was `-10_000`)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_schema.py`:

```python
import unittest

from schema import Period


def period_kwargs(**overrides: object) -> dict:
    value = {
        "id": "test_period",
        "canonical_name": "Test Period",
        "kind": "historical",
        "start": 1000,
        "end": 1500,
        "authority": "test",
        "source_urls": ["https://example.com"],
    }
    value.update(overrides)
    return value


class PeriodTierTests(unittest.TestCase):
    def test_tier_defaults_to_period(self) -> None:
        period = Period(**period_kwargs())
        self.assertEqual(period.tier, "period")

    def test_macro_chapter_tier_is_valid(self) -> None:
        period = Period(**period_kwargs(tier="macro_chapter"))
        self.assertEqual(period.tier, "macro_chapter")

    def test_invalid_tier_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Period(**period_kwargs(tier="subperiod"))  # not a tier value; see design summary #1


class YearFloorTests(unittest.TestCase):
    def test_deep_prehistory_start_is_valid(self) -> None:
        period = Period(**period_kwargs(start=-2_000_000, end=-1_000_000))
        self.assertEqual(period.start, -2_000_000)

    def test_below_new_floor_still_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Period(**period_kwargs(start=-3_000_001, end=-3_000_000))


if __name__ == "__main__":
    unittest.main()
```

Note: `tier` has exactly three values (`macro_chapter`, `regional_era`, `period`) — no separate `subperiod` value. A recursively-nested named period is still `tier: period`; its depth comes from how many hops its `broader_periods` chain takes, not from a distinct tier (see `ONTOLOGY.md`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m unittest tests.test_schema -v`
Expected: failures — `tier` doesn't exist yet, `YEAR_MIN` is still -10,000.

- [ ] **Step 3: Implement the schema changes**

In `schema.py`, change the floor:

```python
YEAR_MIN = -3_000_000
YEAR_MAX = 2100
```

On `Period`, add the field (after `kind`):

```python
    tier: Literal["macro_chapter", "regional_era", "period"] = "period"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m unittest tests.test_schema -v`
Expected: all pass.

- [ ] **Step 5: Run the full suite and build**

Run: `.venv/Scripts/python.exe -m unittest discover -s tests -v` — expect 137 + new tests, all passing.
Run: `.venv/Scripts/python.exe build.py` — expect the same counts as before this task (no data changed yet).

- [ ] **Step 6: Commit**

```bash
git add schema.py tests/test_schema.py
git commit -m "schema: add Period.tier, widen YEAR_MIN to -3M"
```

---

## Task 2: Build-time period-tier hierarchy validation

**Files:**
- Modify: `build.py`
- Create: `tests/test_validate_period_tiers.py`

**Interfaces:**
- Consumes: `Period.tier`, `Period.broader_periods` from Task 1
- Produces: `validate_period_tiers(periods: list[Period]) -> list[str]` (list of error strings, empty if valid), called from `build.py`'s `main()` alongside the existing `load_periods()`/`load_period_links()` calls, fatal on any error (matches `load_all()`'s existing fail-fast pattern for polities)

This can't be a per-record Pydantic validator — it needs to know the tier of the *referenced* period, which means seeing the whole dataset, same reason `find_parent_cycles()` (for polities) already lives in `build.py` rather than `schema.py`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_validate_period_tiers.py`:

```python
import unittest

from build import validate_period_tiers
from schema import Period


def period(id_: str, tier: str, broader: list[str] | None = None) -> Period:
    return Period(
        id=id_,
        canonical_name=id_,
        kind="historical",
        tier=tier,
        start=1000,
        end=1500,
        authority="test",
        source_urls=["https://example.com"],
        broader_periods=broader or [],
    )


class ValidatePeriodTiersTests(unittest.TestCase):
    def test_valid_three_tier_chain_has_no_errors(self) -> None:
        periods = [
            period("macro_a", "macro_chapter"),
            period("regional_a", "regional_era", ["macro_a"]),
            period("period_a", "period", ["regional_a"]),
        ]
        self.assertEqual(validate_period_tiers(periods), [])

    def test_period_may_point_straight_at_macro_chapter(self) -> None:
        periods = [
            period("macro_a", "macro_chapter"),
            period("period_a", "period", ["macro_a"]),
        ]
        self.assertEqual(validate_period_tiers(periods), [])

    def test_macro_chapter_with_a_parent_is_an_error(self) -> None:
        periods = [
            period("macro_a", "macro_chapter"),
            period("macro_b", "macro_chapter", ["macro_a"]),
        ]
        errors = validate_period_tiers(periods)
        self.assertEqual(len(errors), 1)
        self.assertIn("macro_b", errors[0])

    def test_regional_era_with_two_parents_is_an_error(self) -> None:
        periods = [
            period("macro_a", "macro_chapter"),
            period("macro_b", "macro_chapter"),
            period("regional_a", "regional_era", ["macro_a", "macro_b"]),
        ]
        errors = validate_period_tiers(periods)
        self.assertEqual(len(errors), 1)
        self.assertIn("regional_a", errors[0])

    def test_regional_era_parented_to_a_period_is_an_error(self) -> None:
        periods = [
            period("macro_a", "macro_chapter"),
            period("period_a", "period", ["macro_a"]),
            period("regional_a", "regional_era", ["period_a"]),
        ]
        errors = validate_period_tiers(periods)
        self.assertEqual(len(errors), 1)
        self.assertIn("regional_a", errors[0])

    def test_cycle_is_an_error(self) -> None:
        periods = [
            period("macro_a", "macro_chapter"),
            period("period_a", "period", ["period_b"]),
            period("period_b", "period", ["period_a"]),
        ]
        errors = validate_period_tiers(periods)
        self.assertTrue(any("cycle" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_validate_period_tiers -v`
Expected: `ImportError` — `validate_period_tiers` doesn't exist in `build.py` yet.

- [ ] **Step 3: Implement the validator**

Add to `build.py`, near `find_parent_cycles`:

```python
ALLOWED_PARENT_TIERS = {
    "macro_chapter": set(),
    "regional_era": {"macro_chapter"},
    "period": {"macro_chapter", "regional_era", "period"},
}


def validate_period_tiers(periods: list[Period]) -> list[str]:
    by_id = {p.id: p for p in periods}
    errors: list[str] = []
    for p in periods:
        allowed = ALLOWED_PARENT_TIERS[p.tier]
        if p.tier == "macro_chapter":
            if p.broader_periods:
                errors.append(f"{p.id}: tier=macro_chapter must have no broader_periods")
            continue
        if len(p.broader_periods) != 1:
            errors.append(
                f"{p.id}: tier={p.tier} must have exactly one broader_periods entry, "
                f"got {len(p.broader_periods)}"
            )
            continue
        parent_id = p.broader_periods[0]
        parent = by_id.get(parent_id)
        if parent is None:
            continue  # unknown-reference case already reported by load_periods()
        if parent.tier not in allowed:
            errors.append(
                f"{p.id}: tier={p.tier} parent {parent_id!r} has tier={parent.tier!r}, "
                f"must be one of {sorted(allowed)}"
            )
    # cycle detection: walk each period's single-parent chain, watching for revisits
    for p in periods:
        seen = {p.id}
        current = p
        while current.broader_periods:
            parent_id = current.broader_periods[0]
            if parent_id in seen:
                errors.append(f"{p.id}: broader_periods cycle detected at {parent_id!r}")
                break
            seen.add(parent_id)
            parent = by_id.get(parent_id)
            if parent is None:
                break
            current = parent
    return errors
```

Wire it into `main()` right after the existing `period_links = load_period_links(periods, polities)` line:

```python
    tier_errors = validate_period_tiers(periods)
    if tier_errors:
        for e in tier_errors:
            print(f"ERROR  {e}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m unittest tests.test_validate_period_tiers -v`
Expected: all pass.

- [ ] **Step 5: Run build and full suite**

Run: `.venv/Scripts/python.exe build.py` — the 117 existing periods are all `tier: period` with empty `broader_periods` (no tier-mismatch possible yet), so this should still print `OK` with unchanged counts.
Run: `.venv/Scripts/python.exe -m unittest discover -s tests -v` — all green.

- [ ] **Step 6: Commit**

```bash
git add build.py tests/test_validate_period_tiers.py
git commit -m "build: validate period tier hierarchy (allowed parents, cycles)"
```

---

## Task 3: Author the 9 macro chapters

**Files:**
- Create: `periods/macro_human_origins_paleolithic.yaml`
- Create: `periods/macro_agricultural_transitions.yaml`
- Create: `periods/macro_early_cities_states.yaml`
- Create: `periods/macro_classical_imperial_worlds.yaml`
- Create: `periods/macro_postclassical_worlds.yaml`
- Create: `periods/macro_early_modern_connections.yaml`
- Create: `periods/macro_industrial_imperial_world.yaml`
- Create: `periods/macro_world_wars_reordering.yaml`
- Create: `periods/macro_contemporary_world.yaml`
- Test: `tests/test_macro_chapters.py`

**Interfaces:**
- Consumes: `Period.tier` from Task 1, `validate_period_tiers` from Task 2 (these 9 records must pass it: `tier=macro_chapter`, empty `broader_periods`)
- Produces: 9 period ids spanning -3,000,000 to 2100 with no gaps, that Task 4's regional eras point at via `broader_periods`

- [ ] **Step 1: Write the failing test**

Create `tests/test_macro_chapters.py`:

```python
import unittest
from pathlib import Path

import yaml

from schema import Period

ROOT = Path(__file__).resolve().parents[1]
PERIODS_DIR = ROOT / "periods"

EXPECTED_IDS = [
    "macro_human_origins_paleolithic",
    "macro_agricultural_transitions",
    "macro_early_cities_states",
    "macro_classical_imperial_worlds",
    "macro_postclassical_worlds",
    "macro_early_modern_connections",
    "macro_industrial_imperial_world",
    "macro_world_wars_reordering",
    "macro_contemporary_world",
]


class MacroChapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.chapters = []
        for chapter_id in EXPECTED_IDS:
            path = PERIODS_DIR / f"{chapter_id}.yaml"
            self.assertTrue(path.exists(), f"missing {path}")
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.chapters.append(Period.model_validate(data))

    def test_all_nine_exist_with_macro_chapter_tier_and_no_parent(self) -> None:
        self.assertEqual(len(self.chapters), 9)
        for chapter in self.chapters:
            self.assertEqual(chapter.tier, "macro_chapter")
            self.assertEqual(chapter.broader_periods, [])

    def test_chapters_are_contiguous_with_no_gap_or_overlap(self) -> None:
        ordered = sorted(self.chapters, key=lambda c: c.start)
        for earlier, later in zip(ordered, ordered[1:]):
            self.assertEqual(
                earlier.end,
                later.start,
                f"{earlier.id} ends {earlier.end}, {later.id} starts {later.start}",
            )

    def test_span_covers_deep_past_to_present(self) -> None:
        ordered = sorted(self.chapters, key=lambda c: c.start)
        self.assertEqual(ordered[0].start, -3_000_000)
        self.assertEqual(ordered[-1].end, 2100)  # open-ended, modeled as YEAR_MAX

    def test_only_macro_chapters_may_have_empty_continents(self) -> None:
        for chapter in self.chapters:
            self.assertEqual(chapter.geography.continents, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_macro_chapters -v`
Expected: FAIL — none of the 9 files exist yet.

- [ ] **Step 3: Author the 9 files**

`periods/macro_human_origins_paleolithic.yaml`:

```yaml
id: macro_human_origins_paleolithic
canonical_name: Human Origins and Paleolithic Worlds
kind: archaeological
tier: macro_chapter
start: -3000000
end: -10000
start_confidence: low
end_confidence: low
geography:
  continents: []
broader_periods: []
successors: []
authority: 'Histomap editorial: global macro-chapter backbone'
external_ids: {}
notes: Editorial navigation chapter, not a claim that every society developed
  identically. Start is an open lower bound (earliest known stone tools keep
  pushing backward as of 2026); -3,000,000 is a round, citable ballpark
  (Lomekwian/Oldowan toolmaking), not a precise date. Empty continents list
  means deliberately global -- valid only at tier=macro_chapter, see
  ONTOLOGY.md. Dates use astronomical year numbering (year 0 exists),
  inherited from Wikidata via pipeline/wd_to_yaml.py's parse_year().
source_urls:
- https://en.wikipedia.org/wiki/Stone_Age
```

`periods/macro_agricultural_transitions.yaml`:

```yaml
id: macro_agricultural_transitions
canonical_name: Agricultural Transitions and Settled Societies
kind: archaeological
tier: macro_chapter
start: -10000
end: -3500
start_confidence: medium
end_confidence: low
geography:
  continents: []
broader_periods: []
successors: []
authority: 'Histomap editorial: global macro-chapter backbone'
external_ids: {}
notes: Editorial navigation chapter. The Neolithic transition happened at very
  different times on different continents (roughly 10,000 BCE in the Fertile
  Crescent, much later in the Americas) -- this chapter's dates are a global
  envelope, not a claim of simultaneity. See regional_era records for
  per-region dates.
source_urls:
- https://en.wikipedia.org/wiki/Neolithic_Revolution
```

`periods/macro_early_cities_states.yaml`:

```yaml
id: macro_early_cities_states
canonical_name: Early Cities and States
kind: historical
tier: macro_chapter
start: -3500
end: -1200
start_confidence: medium
end_confidence: low
geography:
  continents: []
broader_periods: []
successors: []
authority: 'Histomap editorial: global macro-chapter backbone'
external_ids: {}
notes: Editorial navigation chapter covering the first urban civilizations
  (Mesopotamia, Egypt, Indus Valley, early China) through the Late Bronze
  Age Collapse.
source_urls:
- https://en.wikipedia.org/wiki/Bronze_Age
```

`periods/macro_classical_imperial_worlds.yaml`:

```yaml
id: macro_classical_imperial_worlds
canonical_name: Classical and Imperial Worlds
kind: historical
tier: macro_chapter
start: -1200
end: 500
start_confidence: medium
end_confidence: low
geography:
  continents: []
broader_periods: []
successors: []
authority: 'Histomap editorial: global macro-chapter backbone'
external_ids: {}
notes: Editorial navigation chapter. Covers the Iron Age plus the classical
  and early imperial civilizations of the Mediterranean, Persia, India, and
  China, through the fall of the Western Roman Empire.
source_urls:
- https://en.wikipedia.org/wiki/Classical_antiquity
```

`periods/macro_postclassical_worlds.yaml`:

```yaml
id: macro_postclassical_worlds
canonical_name: Post-Classical Worlds
kind: historical
tier: macro_chapter
start: 500
end: 1500
start_confidence: high
end_confidence: high
geography:
  continents: []
broader_periods: []
successors: []
authority: 'Histomap editorial: global macro-chapter backbone'
external_ids: {}
notes: 'Editorial navigation chapter. Deliberately named "post-classical" rather
  than "medieval" -- medieval is a Eurocentric label that does not describe
  Byzantine, Islamic, African, South Asian, East Asian, or American history in
  this window.'
source_urls:
- https://en.wikipedia.org/wiki/Postclassical_Era
```

`periods/macro_early_modern_connections.yaml`:

```yaml
id: macro_early_modern_connections
canonical_name: Early Modern Global Connections
kind: historical
tier: macro_chapter
start: 1500
end: 1800
start_confidence: high
end_confidence: high
geography:
  continents: []
broader_periods: []
successors: []
authority: 'Histomap editorial: global macro-chapter backbone'
external_ids: {}
notes: Editorial navigation chapter. Maritime expansion, gunpowder empires,
  the Columbian Exchange, and the Scientific Revolution and Enlightenment.
source_urls:
- https://en.wikipedia.org/wiki/Early_modern_period
```

`periods/macro_industrial_imperial_world.yaml`:

```yaml
id: macro_industrial_imperial_world
canonical_name: Industrial and Imperial World
kind: historical
tier: macro_chapter
start: 1800
end: 1914
start_confidence: high
end_confidence: high
geography:
  continents: []
broader_periods: []
successors: []
authority: 'Histomap editorial: global macro-chapter backbone'
external_ids: {}
notes: Editorial navigation chapter. Industrialization, high imperialism, and
  the revolutionary/national movements of the 19th century, through the
  outbreak of the First World War.
source_urls:
- https://en.wikipedia.org/wiki/19th_century
```

`periods/macro_world_wars_reordering.yaml`:

```yaml
id: macro_world_wars_reordering
canonical_name: World Wars and Global Reordering
kind: historical
tier: macro_chapter
start: 1914
end: 1945
start_confidence: high
end_confidence: high
geography:
  continents: []
broader_periods: []
successors: []
authority: 'Histomap editorial: global macro-chapter backbone'
external_ids: {}
notes: Editorial navigation chapter spanning the First World War through the
  end of the Second World War.
source_urls:
- https://en.wikipedia.org/wiki/World_war
```

`periods/macro_contemporary_world.yaml`:

```yaml
id: macro_contemporary_world
canonical_name: Contemporary World
kind: historical
tier: macro_chapter
start: 1945
end: 2100
start_confidence: high
end_confidence: low
geography:
  continents: []
broader_periods: []
successors: []
authority: 'Histomap editorial: global macro-chapter backbone'
external_ids: {}
notes: Editorial navigation chapter, 1945-present. end=2100 is schema.py's
  YEAR_MAX ceiling standing in for "open present" -- Period.end is required
  (unlike Polity.end), so an explicit far-future value is the least surprising
  way to represent "still ongoing." Covers the Cold War, decolonization, the
  post-Cold War era, and the 21st century.
source_urls:
- https://en.wikipedia.org/wiki/Contemporary_history
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m unittest tests.test_macro_chapters -v`
Expected: PASS.

- [ ] **Step 5: Run build and full suite**

Run: `.venv/Scripts/python.exe build.py`
Expected: `117 periods` becomes `126 periods` (117 + 9); polity/entity/transition/link counts unchanged.
Run: `.venv/Scripts/python.exe -m unittest discover -s tests -v`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add periods/macro_*.yaml tests/test_macro_chapters.py
git commit -m "periods: author the 9 global macro chapters"
```

---

## Task 4: Regional eras, two speeds

**Files:**
- Create: `pipeline/seed_regional_eras.py` + `tests/test_seed_regional_eras.py` (hand-curated, chapters 1-5)
- Create: `pipeline/generate_modern_regional_eras.py` + `tests/test_generate_modern_regional_eras.py` (auto-generated, chapters 6-9)
- Create (by running both scripts): `periods/*_era.yaml` — 20 hand-curated + however many continent/chapter combinations the generator finds real polities for

**Interfaces:**
- Consumes: the 9 macro chapter ids from Task 3; for the generator, every `Polity`'s `geography.primary_continent`/`continents` and `start`/`end`
- Produces: `Period` records with `tier: regional_era`, each with exactly one `broader_periods` entry pointing at a macro chapter (satisfying Task 2's validator)

### Part A: hand-curated starter set (chapters 1-5)

- [ ] **Step 1: Write the failing test**

Create `tests/test_seed_regional_eras.py`:

```python
import unittest
from pathlib import Path

import yaml

from pipeline.seed_regional_eras import REGIONAL_ERAS
from schema import Period

ROOT = Path(__file__).resolve().parents[1]
PERIODS_DIR = ROOT / "periods"
VALID_MACRO_CHAPTERS = {
    "macro_human_origins_paleolithic",
    "macro_agricultural_transitions",
    "macro_early_cities_states",
    "macro_classical_imperial_worlds",
    "macro_postclassical_worlds",
}


class SeedRegionalErasTests(unittest.TestCase):
    def test_table_has_twenty_rows(self) -> None:
        self.assertEqual(len(REGIONAL_ERAS), 20)

    def test_every_row_points_at_a_pre_1500_macro_chapter(self) -> None:
        for row in REGIONAL_ERAS:
            self.assertIn(row["broader_periods"][0], VALID_MACRO_CHAPTERS)

    def test_every_row_has_exactly_one_parent(self) -> None:
        for row in REGIONAL_ERAS:
            self.assertEqual(len(row["broader_periods"]), 1)

    def test_ids_are_unique(self) -> None:
        ids = [row["id"] for row in REGIONAL_ERAS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_files_exist_and_validate_after_running(self) -> None:
        for row in REGIONAL_ERAS:
            path = PERIODS_DIR / f"{row['id']}.yaml"
            self.assertTrue(path.exists(), f"missing {path}; run the seed script")
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            period = Period.model_validate(data)
            self.assertEqual(period.tier, "regional_era")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_seed_regional_eras -v`
Expected: `ImportError`.

- [ ] **Step 3: Write the seed script**

Create `pipeline/seed_regional_eras.py`:

```python
"""One-shot authoring script for the hand-curated regional-era starter set
(macro chapters 1-5 only -- Task 4 Part A of the period-ontology plan). Run
once; re-running is safe (overwrites its own files with the same content).
Not part of the recurring pipeline sequence.

# TODO: a few of the auto-built source_urls below (built from canonical_name)
# won't resolve to a real Wikipedia article -- known rough edge, not blocking
# (schema only checks the URL is a string). Fix opportunistically."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PERIODS_DIR = ROOT / "periods"

# (id, canonical_name, macro_chapter_id, start, end, continents, notes)
REGIONAL_ERAS: list[dict] = [
    dict(
        id="african_paleolithic_era",
        canonical_name="African Paleolithic",
        broader_periods=["macro_human_origins_paleolithic"],
        start=-3000000,
        end=-10000,
        continents=["africa"],
        notes="Earliest stone tools and the origin of Homo sapiens.",
    ),
    dict(
        id="eurasian_paleolithic_era",
        canonical_name="Eurasian Paleolithic",
        broader_periods=["macro_human_origins_paleolithic"],
        start=-1800000,
        end=-10000,
        continents=["europe", "asia"],
        notes="From the first Homo erectus dispersal out of Africa (Dmanisi, "
        "~1.8 million years ago) through the end of the last Ice Age.",
    ),
    dict(
        id="fertile_crescent_neolithic_era",
        canonical_name="Fertile Crescent Neolithic",
        broader_periods=["macro_agricultural_transitions"],
        start=-10000,
        end=-3500,
        continents=["asia"],
        notes="Earliest agriculture (Levant, Anatolia, Mesopotamia).",
    ),
    dict(
        id="nile_valley_neolithic_era",
        canonical_name="Nile Valley Neolithic",
        broader_periods=["macro_agricultural_transitions"],
        start=-8800,
        end=-3500,
        continents=["africa"],
        notes="Pre-dynastic Egyptian and Nubian farming cultures.",
    ),
    dict(
        id="east_asian_neolithic_era",
        canonical_name="East Asian Neolithic",
        broader_periods=["macro_agricultural_transitions"],
        start=-7000,
        end=-3500,
        continents=["asia"],
        notes="Yellow and Yangtze river valley farming cultures (e.g. Jiahu, "
        "Hemudu, Yangshao).",
    ),
    dict(
        id="mesoamerican_archaic_era",
        canonical_name="Mesoamerican Archaic",
        broader_periods=["macro_agricultural_transitions"],
        start=-8000,
        end=-2000,
        continents=["north_america"],
        notes="Maize domestication and early sedentism. Ends -2000, well past "
        "this chapter's nominal -3500 boundary -- chapter membership is "
        "editorial, not a date-containment claim; see ONTOLOGY.md.",
    ),
    dict(
        id="andean_archaic_era",
        canonical_name="Andean Archaic",
        broader_periods=["macro_agricultural_transitions"],
        start=-7000,
        end=-2000,
        continents=["south_america"],
        notes="Early Andean and coastal Peruvian farming/fishing settlements "
        "(e.g. Norte Chico). Ends -2000, past this chapter's nominal -3500 "
        "boundary -- see the note on mesoamerican_archaic_era.",
    ),
    dict(
        id="mesopotamian_early_states_era",
        canonical_name="Mesopotamian Early States",
        broader_periods=["macro_early_cities_states"],
        start=-3500,
        end=-1200,
        continents=["asia"],
        notes="Uruk period through the Bronze Age Collapse.",
    ),
    dict(
        id="egyptian_early_states_era",
        canonical_name="Egyptian Early States",
        broader_periods=["macro_early_cities_states"],
        start=-3100,
        end=-1070,
        continents=["africa"],
        notes="Early Dynastic through the New Kingdom. Ends -1070, past this "
        "chapter's nominal -1200 boundary -- editorial placement, not "
        "date-containment; see ONTOLOGY.md.",
    ),
    dict(
        id="east_asian_bronze_age_era",
        canonical_name="East Asian Bronze Age",
        broader_periods=["macro_early_cities_states"],
        start=-2000,
        end=-1046,
        continents=["asia"],
        notes="Erlitou culture through the end of the Shang dynasty.",
    ),
    dict(
        id="european_bronze_age_era",
        canonical_name="European Bronze Age",
        broader_periods=["macro_early_cities_states"],
        start=-3200,
        end=-1200,
        continents=["europe"],
        notes="Aegean, Central European, and Atlantic Bronze Age cultures.",
    ),
    dict(
        id="mediterranean_classical_era",
        canonical_name="Mediterranean Classical Antiquity",
        broader_periods=["macro_classical_imperial_worlds"],
        start=-1200,
        end=500,
        continents=["europe"],
        notes="Greek Dark Age through the fall of the Western Roman Empire.",
    ),
    dict(
        id="east_asian_classical_era",
        canonical_name="East Asian Classical Antiquity",
        broader_periods=["macro_classical_imperial_worlds"],
        start=-1046,
        end=500,
        continents=["asia"],
        notes="Zhou dynasty through the Northern and Southern dynasties.",
    ),
    dict(
        id="south_asian_classical_era",
        canonical_name="South Asian Classical Antiquity",
        broader_periods=["macro_classical_imperial_worlds"],
        start=-600,
        end=500,
        continents=["asia"],
        notes="The Mahajanapadas through the Gupta Empire.",
    ),
    dict(
        id="mesoamerican_formative_classic_era",
        canonical_name="Mesoamerican Formative and Classic Periods",
        broader_periods=["macro_classical_imperial_worlds"],
        start=-1200,
        end=900,
        continents=["north_america"],
        notes="Olmec civilization through the Classic Maya collapse. Ends "
        "900 CE, 400 years past this chapter's nominal 500 CE boundary -- "
        "editorial placement, not date-containment; see ONTOLOGY.md.",
    ),
    dict(
        id="andean_early_civilizations_era",
        canonical_name="Early Andean Civilizations",
        broader_periods=["macro_classical_imperial_worlds"],
        start=-1200,
        end=600,
        continents=["south_america"],
        notes="Chavin culture through the Moche and Nazca. Ends 600 CE, past "
        "this chapter's nominal 500 CE boundary -- see the note on "
        "mesoamerican_formative_classic_era.",
    ),
    dict(
        id="sub_saharan_african_iron_age_era",
        canonical_name="Sub-Saharan African Iron Age",
        broader_periods=["macro_classical_imperial_worlds"],
        start=-600,
        end=500,
        continents=["africa"],
        notes="Nok culture and the early Bantu expansion ironworking "
        "tradition.",
    ),
    dict(
        id="medieval_europe_era",
        canonical_name="Medieval Europe",
        broader_periods=["macro_postclassical_worlds"],
        start=500,
        end=1500,
        continents=["europe"],
        notes="Early, High, and Late Middle Ages, including the Byzantine "
        "Empire.",
    ),
    dict(
        id="islamic_caliphates_era",
        canonical_name="Islamic Caliphates and Sultanates",
        broader_periods=["macro_postclassical_worlds"],
        start=622,
        end=1500,
        continents=["asia", "africa"],
        notes="Rashidun Caliphate through the rise of the Ottoman, Safavid, "
        "and Mughal gunpowder empires.",
    ),
    dict(
        id="east_asian_imperial_era",
        canonical_name="East Asian Imperial Dynasties (Post-Classical)",
        broader_periods=["macro_postclassical_worlds"],
        start=500,
        end=1500,
        continents=["asia"],
        notes="Tang through Ming China; Heian through Muromachi Japan; "
        "Goryeo Korea.",
    ),
]


def build_period(row: dict) -> dict:
    return {
        "id": row["id"],
        "canonical_name": row["canonical_name"],
        "kind": "historical",
        "tier": "regional_era",
        "start": row["start"],
        "end": row["end"],
        "start_confidence": "low",
        "end_confidence": "low",
        "geography": {"continents": row["continents"]},
        "broader_periods": row["broader_periods"],
        "successors": [],
        "authority": "Histomap editorial: regional-era starter set",
        "external_ids": {},
        "notes": row["notes"],
        "source_urls": ["https://en.wikipedia.org/wiki/" + row["canonical_name"].replace(" ", "_")],
    }


def main() -> None:
    for row in REGIONAL_ERAS:
        document = build_period(row)
        path = PERIODS_DIR / f"{row['id']}.yaml"
        path.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    print(f"wrote {len(REGIONAL_ERAS)} regional-era period files")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the script, then the test**

Run: `.venv/Scripts/python.exe -m pipeline.seed_regional_eras`
Expected: `wrote 20 regional-era period files`

Run: `.venv/Scripts/python.exe -m unittest tests.test_seed_regional_eras -v`
Expected: PASS.

### Part B: auto-generated modern regional eras (chapters 6-9)

- [ ] **Step 5: Write the failing test**

Create `tests/test_generate_modern_regional_eras.py`:

```python
import unittest

from pipeline.generate_modern_regional_eras import (
    MODERN_MACRO_CHAPTERS,
    combinations_with_polities,
    era_id,
)


class EraIdTests(unittest.TestCase):
    def test_builds_a_stable_id(self) -> None:
        self.assertEqual(
            era_id("europe", "macro_industrial_imperial_world"),
            "europe_industrial_imperial_world_era",
        )


class CombinationsWithPolitiesTests(unittest.TestCase):
    def test_only_combinations_with_at_least_one_polity_are_returned(self) -> None:
        polities = [
            {"start": 1850, "end": 1900, "geography": {"continents": ["europe"]}},
            {"start": 1000, "end": 1100, "geography": {"continents": ["europe"]}},  # wrong era
            {"start": 1850, "end": None, "geography": {"continents": []}},  # no geography
        ]
        combos = combinations_with_polities(polities, MODERN_MACRO_CHAPTERS)
        self.assertIn(("europe", "macro_industrial_imperial_world"), combos)
        self.assertNotIn(("unknown", "macro_industrial_imperial_world"), combos)

    def test_a_polity_spanning_two_chapters_counts_for_both(self) -> None:
        polities = [
            {"start": 1900, "end": 1950, "geography": {"continents": ["asia"]}},
        ]
        combos = combinations_with_polities(polities, MODERN_MACRO_CHAPTERS)
        self.assertIn(("asia", "macro_industrial_imperial_world"), combos)
        self.assertIn(("asia", "macro_world_wars_reordering"), combos)
        self.assertIn(("asia", "macro_contemporary_world"), combos)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 6: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_generate_modern_regional_eras -v`
Expected: `ImportError`.

- [ ] **Step 7: Write the generator**

Create `pipeline/generate_modern_regional_eras.py`:

```python
"""Data-driven regional-era generator for macro chapters 6-9 (1500-present).
Unlike Task 4 Part A's hand-curated set, this creates a bare continent x
chapter node -- no research, no bespoke naming -- for every combination that
actually has at least one polity in it. Idempotent: rerunning reflects
whatever the dataset currently looks like."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"
PERIODS_DIR = ROOT / "periods"

# (macro_chapter_id, start, end) -- must match periods/macro_*.yaml Task 3 authored
MODERN_MACRO_CHAPTERS = [
    ("macro_early_modern_connections", 1500, 1800),
    ("macro_industrial_imperial_world", 1800, 1914),
    ("macro_world_wars_reordering", 1914, 1945),
    ("macro_contemporary_world", 1945, 2100),
]


def era_id(continent: str, chapter_id: str) -> str:
    return f"{continent}_{chapter_id.removeprefix('macro_')}_era"


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def combinations_with_polities(
    polities: list[dict], macro_chapters: list[tuple[str, int, int]]
) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for polity in polities:
        continents = (polity.get("geography") or {}).get("continents") or []
        if not continents:
            continue
        p_start = polity["start"]
        p_end = polity.get("end") if polity.get("end") is not None else 2026
        for chapter_id, c_start, c_end in macro_chapters:
            if _overlap(p_start, p_end, c_start, c_end):
                for continent in continents:
                    found.add((continent, chapter_id))
    return found


def build_period(continent: str, chapter_id: str, start: int, end: int) -> dict:
    return {
        "id": era_id(continent, chapter_id),
        "canonical_name": f"{continent.replace('_', ' ').title()}, "
        f"{chapter_id.removeprefix('macro_').replace('_', ' ').title()}",
        "kind": "historical",
        "tier": "regional_era",
        "start": start,
        "end": end,
        "start_confidence": "low",
        "end_confidence": "low",
        "geography": {"continents": [continent]},
        "broader_periods": [chapter_id],
        "successors": [],
        "authority": "Histomap editorial: auto-generated continent x chapter node",
        "external_ids": {},
        "notes": "Auto-generated placeholder -- continent-level grain only, no "
        "historical research. A real sub-continental regional era (added by "
        "hand, the Task 4 Part A way) can replace this once someone wants to "
        "invest that research; see ONTOLOGY.md.",
        "source_urls": [],
    }


def load_polities() -> list[dict]:
    documents = []
    for path in sorted(POLITIES_DIR.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if document.get("timeline_role") == "period":
            continue
        documents.append(document)
    return documents


def main() -> None:
    polities = load_polities()
    combos = combinations_with_polities(polities, MODERN_MACRO_CHAPTERS)
    chapter_ranges = {chapter_id: (start, end) for chapter_id, start, end in MODERN_MACRO_CHAPTERS}
    for continent, chapter_id in sorted(combos):
        start, end = chapter_ranges[chapter_id]
        document = build_period(continent, chapter_id, start, end)
        path = PERIODS_DIR / f"{document['id']}.yaml"
        path.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    print(f"wrote {len(combos)} auto-generated regional-era period files")


if __name__ == "__main__":
    main()
```

`source_urls: []` deliberately breaks the `Period` schema's `min_length=1` requirement on that field for auto-generated rows without a real source — check `schema.py`'s current `Period.source_urls` definition before running this; if it still says `Field(default_factory=list, min_length=1)`, either relax it to allow empty for auto-generated rows (simplest: drop `min_length=1`, since nothing else in this plan relies on periods always having a source) or generate a placeholder Wikipedia-continent-article URL instead (less honest — prefer relaxing the constraint).

- [ ] **Step 8: Run test, resolve the `source_urls` constraint, then run the generator**

Run: `.venv/Scripts/python.exe -m unittest tests.test_generate_modern_regional_eras -v`
Expected: PASS (pure logic test, no file I/O, unaffected by the schema question above).

If `Period.source_urls` still requires `min_length=1`, edit `schema.py`:

```python
    source_urls: list[str] = Field(default_factory=list)
```

(removing `min_length=1`). This is a real, intentional loosening — auto-generated placeholder rows are explicitly less-sourced than everything else in this dataset, and the field should allow saying so rather than forcing a fake citation.

Run: `.venv/Scripts/python.exe -m pipeline.generate_modern_regional_eras`
Expected: `wrote N auto-generated regional-era period files` (N depends on the live dataset's continent/date coverage — expect somewhere in the 15-25 range given 6 continents x 4 chapters minus combinations with zero polities, e.g. Antarctica).

- [ ] **Step 9: Run build and full suite**

Run: `.venv/Scripts/python.exe build.py`
Expected: `146 periods` (126 after Task 3 + 20 from Part A) plus however many Part B generated.
Run: `.venv/Scripts/python.exe -m unittest discover -s tests -v`
Expected: all green.

- [ ] **Step 10: Commit**

```bash
git add pipeline/seed_regional_eras.py pipeline/generate_modern_regional_eras.py periods/*_era.yaml tests/test_seed_regional_eras.py tests/test_generate_modern_regional_eras.py schema.py
git commit -m "periods: author 20 curated + auto-generate modern regional eras"
```

---

## Task 5: Suggest regional-era links for the 117 pre-existing periods

**Files:**
- Create: `pipeline/suggest_regional_eras.py`
- Test: `tests/test_suggest_regional_eras.py`
- Create (script output): `reports/regional_era_suggestions.jsonl`, `reports/regional_era_summary.md`

**Interfaces:**
- Consumes: `Period.geography.primary_continent`/`continents`, `Period.start`/`end`, all `tier: regional_era` records from Task 4
- Produces: a JSONL suggestion queue (same shape as `reports/period_role_review.jsonl` from `pipeline/classify_period_roles.py`) — suggests, does not write `broader_periods` directly

Scoring: continent overlap required, then rank by overlap-year count (ties broken alphabetically by id).

- [ ] **Step 1: Write the failing test**

Create `tests/test_suggest_regional_eras.py`:

```python
import unittest

from pipeline.suggest_regional_eras import overlap_years, rank_candidates


class OverlapYearsTests(unittest.TestCase):
    def test_full_containment(self) -> None:
        self.assertEqual(overlap_years((500, 600), (0, 1000)), 100)

    def test_partial_overlap(self) -> None:
        self.assertEqual(overlap_years((900, 1100), (500, 1000)), 100)

    def test_no_overlap_returns_zero(self) -> None:
        self.assertEqual(overlap_years((0, 100), (200, 300)), 0)

    def test_touching_ranges_return_zero(self) -> None:
        self.assertEqual(overlap_years((0, 100), (100, 200)), 0)


class RankCandidatesTests(unittest.TestCase):
    def test_picks_the_best_overlap(self) -> None:
        period = {"start": 900, "end": 1000, "geography": {"continents": ["europe"]}}
        candidates = [
            {"id": "b", "start": 500, "end": 950, "geography": {"continents": ["europe"]}},
            {"id": "a", "start": 800, "end": 1100, "geography": {"continents": ["europe"]}},
        ]
        ranked = rank_candidates(period, candidates)
        self.assertEqual(ranked[0]["id"], "a")

    def test_filters_out_non_overlapping_continent(self) -> None:
        period = {"start": 900, "end": 1000, "geography": {"continents": ["asia"]}}
        candidates = [
            {"id": "a", "start": 800, "end": 1100, "geography": {"continents": ["europe"]}},
        ]
        self.assertEqual(rank_candidates(period, candidates), [])

    def test_ties_broken_alphabetically(self) -> None:
        period = {"start": 900, "end": 1000, "geography": {"continents": ["europe"]}}
        candidates = [
            {"id": "z_era", "start": 800, "end": 1100, "geography": {"continents": ["europe"]}},
            {"id": "a_era", "start": 800, "end": 1100, "geography": {"continents": ["europe"]}},
        ]
        ranked = rank_candidates(period, candidates)
        self.assertEqual(ranked[0]["id"], "a_era")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_suggest_regional_eras -v`
Expected: `ImportError`.

- [ ] **Step 3: Write the suggester**

Create `pipeline/suggest_regional_eras.py`:

```python
"""Pipeline step: suggest a regional_era broader_period for each tier=period
record that doesn't have one yet, by continent + date-range overlap against
every tier=regional_era record. Writes a review queue; does not modify
periods/*.yaml directly."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PERIODS_DIR = ROOT / "periods"
REPORT_PATH = ROOT / "reports" / "regional_era_suggestions.jsonl"
SUMMARY_PATH = ROOT / "reports" / "regional_era_summary.md"


def overlap_years(a: tuple[int, int], b: tuple[int, int]) -> int:
    lo = max(a[0], b[0])
    hi = min(a[1], b[1])
    return max(0, hi - lo)


def rank_candidates(period: dict, candidates: list[dict]) -> list[dict]:
    period_continents = set((period.get("geography") or {}).get("continents") or [])
    period_range = (period["start"], period["end"])
    scored = []
    for candidate in candidates:
        candidate_continents = set((candidate.get("geography") or {}).get("continents") or [])
        if not (period_continents & candidate_continents):
            continue
        candidate_range = (candidate["start"], candidate["end"])
        years = overlap_years(period_range, candidate_range)
        if years <= 0:
            continue
        scored.append((years, candidate["id"], candidate))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [candidate for _years, _id, candidate in scored]


def load_regional_eras() -> list[dict]:
    eras = []
    for path in sorted(PERIODS_DIR.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if document.get("tier") == "regional_era":
            eras.append(document)
    return eras


def main() -> None:
    regional_eras = load_regional_eras()
    suggestions = []
    unmatched = 0
    for path in sorted(PERIODS_DIR.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if document.get("tier", "period") != "period":
            continue
        if document.get("broader_periods"):
            continue  # already linked
        ranked = rank_candidates(document, regional_eras)
        if not ranked:
            unmatched += 1
            continue
        suggestions.append(
            {
                "period_id": document["id"],
                "canonical_name": document["canonical_name"],
                "top_suggestion": ranked[0]["id"],
                "alternatives": [r["id"] for r in ranked[1:3]],
            }
        )
    REPORT_PATH.write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in suggestions) + "\n",
        encoding="utf-8",
    )
    SUMMARY_PATH.write_text(
        "# Regional-era suggestions\n\n"
        f"- Suggested: {len(suggestions)}\n"
        f"- Unmatched (no continent+date overlap with any regional era): {unmatched}\n"
        "\nUnmatched periods are not a bug -- after Task 4 Part B, coverage should be "
        "close to complete, but any period whose geography is unset, or whose dates "
        "fall entirely in a gap, will legitimately have no suggestion.\n",
        encoding="utf-8",
    )
    print(f"suggested {len(suggestions)}, unmatched {unmatched}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the script, then the test**

Run: `.venv/Scripts/python.exe -m unittest tests.test_suggest_regional_eras -v`
Expected: PASS.

Run: `.venv/Scripts/python.exe -m pipeline.suggest_regional_eras`
Expected: prints `suggested N, unmatched M` and writes the two report files.

- [ ] **Step 5: Read the output, run build and full suite, commit**

Run:
```bash
head -5 reports/regional_era_suggestions.jsonl
cat reports/regional_era_summary.md
```

Run: `.venv/Scripts/python.exe build.py` and `.venv/Scripts/python.exe -m unittest discover -s tests -v` — both green, no data changed (report-only task).

```bash
git add pipeline/suggest_regional_eras.py tests/test_suggest_regional_eras.py reports/regional_era_suggestions.jsonl reports/regional_era_summary.md
git commit -m "pipeline: suggest regional-era links for existing periods (review queue)"
```

---

## Task 6: Suggest polity → period links

**Files:**
- Create: `pipeline/suggest_period_links.py`
- Test: `tests/test_suggest_period_links.py`
- Create (script output): `reports/period_link_suggestions.jsonl`, `reports/period_link_suggestion_summary.md`

**Interfaces:**
- Consumes: `Polity.geography`, `Polity.start`/`end`, `Polity.visibility_tier`/`visibility_override`, all `Period` records (any tier), existing `period_links.yaml`
- Produces: a review queue ranking, for each unlinked in-scope polity, its best-matching period (any tier, preferring the most specific)

Scoped to `visibility_tier in {"global", "regional"}` or `visibility_override` set — the few hundred most prominent polities, matching where a first version of the timeline UI would show polities at the top zoom levels. Full coverage of all 4,671 is future work, same as every other review queue.

- [ ] **Step 1: Write the failing test**

Create `tests/test_suggest_period_links.py`:

```python
import unittest

from pipeline.suggest_period_links import best_period_for_polity, in_scope


class InScopeTests(unittest.TestCase):
    def test_global_tier_in_scope(self) -> None:
        self.assertTrue(in_scope({"visibility_tier": "global"}))

    def test_regional_tier_in_scope(self) -> None:
        self.assertTrue(in_scope({"visibility_tier": "regional"}))

    def test_detailed_tier_out_of_scope_without_override(self) -> None:
        self.assertFalse(in_scope({"visibility_tier": "detailed"}))

    def test_detailed_tier_with_override_in_scope(self) -> None:
        self.assertTrue(
            in_scope({"visibility_tier": "detailed", "visibility_override": "global"})
        )


class BestPeriodForPolityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.periods = [
            {
                "id": "macro_postclassical_worlds",
                "tier": "macro_chapter",
                "start": 500,
                "end": 1500,
                "geography": {"continents": []},
            },
            {
                "id": "medieval_europe_era",
                "tier": "regional_era",
                "start": 500,
                "end": 1500,
                "geography": {"continents": ["europe"]},
            },
            {
                "id": "viking_age_period",
                "tier": "period",
                "start": 793,
                "end": 1066,
                "geography": {"continents": ["europe"]},
            },
        ]

    def test_prefers_most_specific_tier_when_all_overlap(self) -> None:
        polity = {"start": 900, "end": 950, "geography": {"continents": ["europe"]}}
        best = best_period_for_polity(polity, self.periods)
        self.assertEqual(best["id"], "viking_age_period")

    def test_falls_back_to_regional_era_when_no_period_matches(self) -> None:
        polity = {"start": 1200, "end": 1300, "geography": {"continents": ["europe"]}}
        best = best_period_for_polity(polity, self.periods)
        self.assertEqual(best["id"], "medieval_europe_era")

    def test_falls_back_to_macro_chapter_when_no_geography(self) -> None:
        polity = {"start": 1200, "end": 1300, "geography": {"continents": []}}
        best = best_period_for_polity(polity, self.periods)
        self.assertEqual(best["id"], "macro_postclassical_worlds")

    def test_returns_none_when_nothing_overlaps(self) -> None:
        polity = {"start": 2000, "end": 2020, "geography": {"continents": ["europe"]}}
        self.assertIsNone(best_period_for_polity(polity, self.periods))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_suggest_period_links -v`
Expected: `ImportError`.

- [ ] **Step 3: Write the suggester**

Create `pipeline/suggest_period_links.py`:

```python
"""Pipeline step: suggest a period_links.yaml entry for global/regional-tier
polities that don't have one yet. Writes a review queue; does not modify
period_links.yaml directly."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"
PERIODS_DIR = ROOT / "periods"
PERIOD_LINKS_PATH = ROOT / "period_links.yaml"
REPORT_PATH = ROOT / "reports" / "period_link_suggestions.jsonl"
SUMMARY_PATH = ROOT / "reports" / "period_link_suggestion_summary.md"

TIER_SPECIFICITY = {"period": 0, "regional_era": 1, "macro_chapter": 2}


def in_scope(polity: dict) -> bool:
    if polity.get("visibility_override") == "global":
        return True
    return polity.get("visibility_tier") in {"global", "regional"}


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> int:
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    return max(0, hi - lo)


def best_period_for_polity(polity: dict, periods: list[dict]) -> dict | None:
    polity_continents = set((polity.get("geography") or {}).get("continents") or [])
    polity_range = (polity["start"], polity.get("end") if polity.get("end") is not None else 2026)
    candidates = []
    for period in periods:
        period_continents = set((period.get("geography") or {}).get("continents") or [])
        # macro chapters have continents=[] (deliberately global, tier-scoped -- see
        # ONTOLOGY.md) -- always geography-eligible; any other empty-continents period
        # is unclassified, not global, so it's correctly excluded by this same check.
        if period_continents and not (polity_continents & period_continents):
            continue
        period_range = (period["start"], period["end"])
        years = _overlap(polity_range, period_range)
        if years <= 0:
            continue
        specificity = TIER_SPECIFICITY.get(period.get("tier", "period"), 0)
        candidates.append((specificity, -years, period["id"], period))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][3]


def load_periods() -> list[dict]:
    return [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(PERIODS_DIR.glob("*.yaml"))
    ]


def load_linked_polity_ids() -> set[str]:
    if not PERIOD_LINKS_PATH.exists():
        return set()
    links = yaml.safe_load(PERIOD_LINKS_PATH.read_text(encoding="utf-8")) or []
    return {link["entity_id"] for link in links}


def main() -> None:
    periods = load_periods()
    already_linked = load_linked_polity_ids()
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
            continue
        best = best_period_for_polity(polity, periods)
        if best is None:
            unmatched += 1
            continue
        suggestions.append(
            {
                "entity_id": polity["id"],
                "canonical_name": polity["canonical_name"],
                "suggested_period_id": best["id"],
                "suggested_tier": best.get("tier", "period"),
            }
        )
    REPORT_PATH.write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in suggestions) + "\n",
        encoding="utf-8",
    )
    SUMMARY_PATH.write_text(
        "# Polity to period-link suggestions\n\n"
        f"- In-scope polities (global/regional tier or visibility_override): {in_scope_count}\n"
        f"- Already linked: {in_scope_count - len(suggestions) - unmatched}\n"
        f"- Suggested: {len(suggestions)}\n"
        f"- Unmatched (no geography/date overlap with any period): {unmatched}\n",
        encoding="utf-8",
    )
    print(f"in-scope {in_scope_count}, suggested {len(suggestions)}, unmatched {unmatched}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the script, then the test**

Run: `.venv/Scripts/python.exe -m unittest tests.test_suggest_period_links -v`
Expected: PASS.

Run: `.venv/Scripts/python.exe -m pipeline.suggest_period_links`
Expected: prints `in-scope N, suggested M, unmatched K` and writes the two report files. After Task 4 Part B, `unmatched` should be small — every in-scope polity now has at least a continent/chapter node to fall back to.

- [ ] **Step 5: Read the output, run build and full suite, commit**

Run: `cat reports/period_link_suggestion_summary.md`

Run: `.venv/Scripts/python.exe build.py` and `.venv/Scripts/python.exe -m unittest discover -s tests -v` — both green, no polity/period data changed (report-only task).

```bash
git add pipeline/suggest_period_links.py tests/test_suggest_period_links.py reports/period_link_suggestions.jsonl reports/period_link_suggestion_summary.md
git commit -m "pipeline: suggest period links for global/regional-tier polities"
```

---

## Task 7: Hierarchy query layer

**Files:**
- Create: `pipeline/period_hierarchy.py`
- Test: `tests/test_period_hierarchy.py`

**Interfaces:**
- Consumes: `periods/*.yaml` (`tier`, `broader_periods` — single-parent by convention per Task 2/4), `period_links.yaml` (`period_id`, `entity_id`), `polities/*.yaml` (`prominence_score`, `visibility_override`) for `top_entities`
- Produces:
  - `PeriodHierarchy.ancestors(period_id: str) -> list[str]` — single-chain breadcrumb from a period up to its macro chapter, root-first; raises `ValueError` on a cycle instead of hanging
  - `PeriodHierarchy.children(period_id: str) -> list[str]` — direct child period ids, ordered by `start`
  - `PeriodHierarchy.entities_under(period_id: str) -> list[str]` — deduplicated polity ids linked to this period or any period in its subtree
  - `PeriodHierarchy.top_entities(period_id: str, limit: int) -> list[str]` — `entities_under()`, ranked: `visibility_override` set first, then `prominence_score` descending
  - `PeriodHierarchy.macro_chapters() -> list[str]` — the 9 top-level ids, ordered by `start`

- [ ] **Step 1: Write the failing test**

Create `tests/test_period_hierarchy.py`:

```python
import unittest

from pipeline.period_hierarchy import PeriodHierarchy


def build_hierarchy(polities: list[dict] | None = None) -> PeriodHierarchy:
    periods = [
        {"id": "macro_a", "tier": "macro_chapter", "start": 0, "broader_periods": []},
        {"id": "regional_a", "tier": "regional_era", "start": 100, "broader_periods": ["macro_a"]},
        {"id": "period_a", "tier": "period", "start": 200, "broader_periods": ["regional_a"]},
        {"id": "period_b", "tier": "period", "start": 300, "broader_periods": ["regional_a"]},
    ]
    links = [
        {"period_id": "period_a", "entity_id": "polity_1"},
        {"period_id": "period_a", "entity_id": "polity_2"},
        {"period_id": "period_b", "entity_id": "polity_3"},
        {"period_id": "regional_a", "entity_id": "polity_4"},
    ]
    return PeriodHierarchy(periods=periods, period_links=links, polities=polities or [])


class AncestorsTests(unittest.TestCase):
    def test_root_first_chain(self) -> None:
        hierarchy = build_hierarchy()
        self.assertEqual(hierarchy.ancestors("period_a"), ["macro_a", "regional_a"])

    def test_macro_chapter_has_no_ancestors(self) -> None:
        hierarchy = build_hierarchy()
        self.assertEqual(hierarchy.ancestors("macro_a"), [])

    def test_unknown_id_raises(self) -> None:
        hierarchy = build_hierarchy()
        with self.assertRaises(KeyError):
            hierarchy.ancestors("does_not_exist")

    def test_cycle_raises_instead_of_hanging(self) -> None:
        periods = [
            {"id": "loop_a", "tier": "period", "start": 0, "broader_periods": ["loop_b"]},
            {"id": "loop_b", "tier": "period", "start": 0, "broader_periods": ["loop_a"]},
        ]
        hierarchy = PeriodHierarchy(periods=periods, period_links=[], polities=[])
        with self.assertRaises(ValueError):
            hierarchy.ancestors("loop_a")


class ChildrenTests(unittest.TestCase):
    def test_direct_children_ordered_by_start(self) -> None:
        hierarchy = build_hierarchy()
        self.assertEqual(hierarchy.children("regional_a"), ["period_a", "period_b"])

    def test_leaf_has_no_children(self) -> None:
        hierarchy = build_hierarchy()
        self.assertEqual(hierarchy.children("period_a"), [])


class EntitiesUnderTests(unittest.TestCase):
    def test_leaf_period_returns_its_own_links(self) -> None:
        hierarchy = build_hierarchy()
        self.assertEqual(sorted(hierarchy.entities_under("period_a")), ["polity_1", "polity_2"])

    def test_ancestor_returns_transitive_deduplicated_links(self) -> None:
        hierarchy = build_hierarchy()
        self.assertEqual(
            sorted(hierarchy.entities_under("regional_a")),
            ["polity_1", "polity_2", "polity_3", "polity_4"],
        )

    def test_macro_chapter_returns_everything_under_it(self) -> None:
        hierarchy = build_hierarchy()
        self.assertEqual(
            sorted(hierarchy.entities_under("macro_a")),
            ["polity_1", "polity_2", "polity_3", "polity_4"],
        )


class TopEntitiesTests(unittest.TestCase):
    def test_ranks_by_prominence_score_descending(self) -> None:
        polities = [
            {"id": "polity_1", "prominence_score": 10},
            {"id": "polity_2", "prominence_score": 90},
            {"id": "polity_3", "prominence_score": 50},
            {"id": "polity_4", "prominence_score": 30},
        ]
        hierarchy = build_hierarchy(polities)
        self.assertEqual(
            hierarchy.top_entities("macro_a", limit=2),
            ["polity_2", "polity_3"],
        )

    def test_visibility_override_is_pinned_first(self) -> None:
        polities = [
            {"id": "polity_1", "prominence_score": 10, "visibility_override": "global"},
            {"id": "polity_2", "prominence_score": 90},
        ]
        hierarchy = build_hierarchy(polities)
        self.assertEqual(hierarchy.top_entities("macro_a", limit=1), ["polity_1"])


class MacroChaptersTests(unittest.TestCase):
    def test_orders_by_start(self) -> None:
        periods = [
            {"id": "macro_b", "tier": "macro_chapter", "start": 500, "broader_periods": []},
            {"id": "macro_a", "tier": "macro_chapter", "start": 0, "broader_periods": []},
        ]
        hierarchy = PeriodHierarchy(periods=periods, period_links=[], polities=[])
        self.assertEqual(hierarchy.macro_chapters(), ["macro_a", "macro_b"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_period_hierarchy -v`
Expected: `ImportError`.

- [ ] **Step 3: Write the query layer**

Create `pipeline/period_hierarchy.py`:

```python
"""Read-side query layer over the period tier hierarchy (periods/*.yaml +
period_links.yaml + polities/*.yaml). This is what a future timeline UI/API
should import instead of re-deriving broader_periods/period_links traversal,
or reading the retired visibility_tier field, itself."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PERIODS_DIR = ROOT / "periods"
POLITIES_DIR = ROOT / "polities"
PERIOD_LINKS_PATH = ROOT / "period_links.yaml"


class PeriodHierarchy:
    def __init__(
        self, periods: list[dict], period_links: list[dict], polities: list[dict]
    ) -> None:
        self._periods = {p["id"]: p for p in periods}
        self._children: dict[str, list[str]] = {}
        for period in periods:
            for parent_id in period.get("broader_periods") or []:
                self._children.setdefault(parent_id, []).append(period["id"])
        for parent_id, child_ids in self._children.items():
            child_ids.sort(key=lambda cid: self._periods[cid]["start"])
        self._direct_links: dict[str, list[str]] = {}
        for link in period_links:
            self._direct_links.setdefault(link["period_id"], []).append(link["entity_id"])
        self._polities = {p["id"]: p for p in polities}

    def ancestors(self, period_id: str) -> list[str]:
        period = self._periods[period_id]  # KeyError on unknown id, by design
        chain: list[str] = []
        seen = {period_id}
        current = period
        while current.get("broader_periods"):
            parent_id = current["broader_periods"][0]
            if parent_id in seen:
                raise ValueError(f"broader_periods cycle detected at {parent_id!r}")
            seen.add(parent_id)
            chain.append(parent_id)
            current = self._periods[parent_id]
        return list(reversed(chain))

    def children(self, period_id: str) -> list[str]:
        return list(self._children.get(period_id, []))

    def entities_under(self, period_id: str) -> list[str]:
        entities: set[str] = set(self._direct_links.get(period_id, []))
        stack = list(self._children.get(period_id, []))
        seen_periods = {period_id}
        while stack:
            current_id = stack.pop()
            if current_id in seen_periods:
                continue
            seen_periods.add(current_id)
            entities.update(self._direct_links.get(current_id, []))
            stack.extend(self._children.get(current_id, []))
        return list(entities)

    def top_entities(self, period_id: str, limit: int) -> list[str]:
        entity_ids = self.entities_under(period_id)

        def sort_key(entity_id: str) -> tuple[int, float]:
            polity = self._polities.get(entity_id, {})
            pinned = 0 if polity.get("visibility_override") else 1
            return (pinned, -polity.get("prominence_score", 0))

        return sorted(entity_ids, key=sort_key)[:limit]

    def macro_chapters(self) -> list[str]:
        chapters = [p for p in self._periods.values() if p.get("tier") == "macro_chapter"]
        chapters.sort(key=lambda p: p["start"])
        return [p["id"] for p in chapters]


def load() -> PeriodHierarchy:
    periods = [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(PERIODS_DIR.glob("*.yaml"))
    ]
    period_links = (
        yaml.safe_load(PERIOD_LINKS_PATH.read_text(encoding="utf-8"))
        if PERIOD_LINKS_PATH.exists()
        else []
    ) or []
    polities = [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(POLITIES_DIR.glob("*.yaml"))
    ]
    return PeriodHierarchy(periods=periods, period_links=period_links, polities=polities)


if __name__ == "__main__":
    hierarchy = load()
    for chapter_id in hierarchy.macro_chapters():
        count = len(hierarchy.entities_under(chapter_id))
        top = hierarchy.top_entities(chapter_id, limit=3)
        print(f"{chapter_id}: {count} linked entities, top 3: {top}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m unittest tests.test_period_hierarchy -v`
Expected: PASS.

- [ ] **Step 5: Run it against the real dataset, run build and full suite**

Run: `.venv/Scripts/python.exe -m pipeline.period_hierarchy`
Expected: 9 lines, one per macro chapter, with entity counts reflecting `period_links.yaml`'s current size after Task 6 (this task builds the query layer, it doesn't apply Task 6's suggestions itself).

Run: `.venv/Scripts/python.exe build.py` and `.venv/Scripts/python.exe -m unittest discover -s tests -v` — both green.

- [ ] **Step 6: Commit**

```bash
git add pipeline/period_hierarchy.py tests/test_period_hierarchy.py
git commit -m "pipeline: add period_hierarchy query layer (ancestors/children/top_entities)"
```

---

## Task 8: Retire the competitive visibility-tier algorithm

**Files:**
- Modify: `pipeline/compute_prominence.py`
- Modify: `tests/test_compute_prominence.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `compute()` still returns updated `prominence_score`/`prominence_components` per record; no longer touches `visibility_tier`. `balanced_visibility`, `_top_per_stratum`, `visibility_stratum`, `historical_era`, `tier_for` are deleted, not deprecated-in-place — `ONTOLOGY.md` explains why freezing in place wasn't enough (dead code implying an algorithm is still authoritative when it isn't).

Read `pipeline/compute_prominence.py` in full before starting — this task edits an existing, working file; know what's around each change before making it.

- [ ] **Step 1: Update the test file first (red)**

Rewrite `tests/test_compute_prominence.py`:

```python
import tempfile
import unittest
from pathlib import Path

import yaml

from pipeline.compute_prominence import compute, prominence_components, score_prominence


def document(entity_id: str, score: float, **overrides: object) -> dict:
    value = {
        "id": entity_id,
        "canonical_name": entity_id.replace("_", " ").title(),
        "start": 1000,
        "end": 1500,
        "entity_type": "polity",
        "entity_type_confidence": "high",
        "eligibility": "accepted",
        "geography": {"continents": ["europe"], "primary_continent": "europe"},
        "prominence_score": score,
        "prominence_components": {},
        "visibility_tier": "detailed",
        "external_ids": {},
    }
    value.update(overrides)
    return value


class ProminenceComponentsTests(unittest.TestCase):
    def test_components_are_capped_and_sum_to_total(self) -> None:
        components = prominence_components(
            sitelinks=100_000,
            start=-10_000,
            end=None,
            authority_coverage=50,
            historical_evidence=50,
            relationship_degree=1_000,
            transition_count=20,
            editorial_score=50,
        )
        self.assertEqual(components["wikidata_reach"], 30)
        self.assertEqual(components["authority_coverage"], 20)
        self.assertEqual(components["historical_evidence"], 20)
        self.assertEqual(components["relationship_centrality"], 15)
        self.assertEqual(components["longevity"], 8)
        self.assertEqual(components["editorial_work"], 7)
        self.assertEqual(components["total"], 100)

    def test_present_country_does_not_imply_subordination(self) -> None:
        common = dict(sitelinks=25, start=1800, end=None, authoritative=False, editorial=False)
        self.assertEqual(
            score_prominence(**common, has_parent_country=False),
            score_prominence(**common, has_parent_country=True),
        )

    def test_uncertainty_and_aggregate_penalties_are_explicit(self) -> None:
        certain = prominence_components(sitelinks=50, start=1000, end=1500)
        uncertain = prominence_components(
            sitelinks=50,
            start=1000,
            end=1500,
            entity_type_confidence="low",
            start_confidence="legendary",
            end_confidence="low",
            aggregate=True,
        )
        self.assertEqual(uncertain["type_uncertainty_penalty"], -10)
        self.assertEqual(uncertain["date_uncertainty_penalty"], -5)
        self.assertEqual(uncertain["aggregate_penalty"], -25)
        self.assertGreater(certain["total"], uncertain["total"])


class ComputeDoesNotTouchVisibilityTierTests(unittest.TestCase):
    def test_visibility_tier_is_left_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            polities_dir = Path(tmp) / "polities"
            polities_dir.mkdir()
            cache_path = Path(tmp) / "sitelinks.json"
            doc = document("test_polity", score=0)
            doc["visibility_tier"] = "global"  # deliberately pre-set, no wikidata id -> offline-safe
            (polities_dir / "test_polity.yaml").write_text(
                yaml.safe_dump(doc, sort_keys=False), encoding="utf-8"
            )

            compute(polities_dir=polities_dir, cache_path=cache_path, offline=True)

            written = yaml.safe_load((polities_dir / "test_polity.yaml").read_text(encoding="utf-8"))
            self.assertEqual(written["visibility_tier"], "global")  # unchanged
            self.assertIn("prominence_score", written)  # still recomputed


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify the compute-side ones fail**

Run: `.venv/Scripts/python.exe -m unittest tests.test_compute_prominence -v`
Expected: `ProminenceComponentsTests` pass unchanged (nothing about them changed yet). `ComputeDoesNotTouchVisibilityTierTests` currently **fails** — today's `compute()` calls `balanced_visibility()`, which will overwrite `visibility_tier` based on score, not leave the pre-set `"global"` alone.

- [ ] **Step 3: Delete the competitive algorithm from `pipeline/compute_prominence.py`**

Remove these five functions and their supporting module-level constants entirely (not commented out, not renamed — deleted): `tier_for`, `historical_era`, `visibility_stratum`, `_top_per_stratum`, `balanced_visibility`, and the now-unused constants `GLOBAL_ABSOLUTE_COUNT`, `GLOBAL_PER_STRATUM`, `REGIONAL_ABSOLUTE_COUNT`, `REGIONAL_PER_STRATUM`, `CONTEXT_TYPES`, `NORMAL_TYPES` (all only referenced by the deleted functions). Also drop the now-unused `from collections import defaultdict` import **only if** nothing else in the file still uses `defaultdict` — check first, since `compute()`'s `transition_counts`/`inbound` dictionaries also use it and must stay.

In `compute()`, replace:

```python
    counts = balanced_visibility(documents)
    for path, document in zip(paths, documents, strict=True):
        path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
    REPORT_PATH.write_text(
        "# Prominence and visibility\n\n"
        + "\n".join(f"- {name.title()}: {count:,}" for name, count in counts.items())
        + f"\n- Global absolute shortlist: {GLOBAL_ABSOLUTE_COUNT}\n"
        + f"- Global per continent/era: {GLOBAL_PER_STRATUM}\n"
        + f"- Regional absolute shortlist: {REGIONAL_ABSOLUTE_COUNT}\n"
        + f"- Regional per continent/era: {REGIONAL_PER_STRATUM}\n",
        encoding="utf-8",
    )
    return counts
```

with:

```python
    for path, document in zip(paths, documents, strict=True):
        path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
    scores = [document["prominence_score"] for document in documents]
    REPORT_PATH.write_text(
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
    return {"scored": len(scores)}
```

Update `compute()`'s docstring reference and return type annotation (`-> dict[str, int]` stays accurate — just a different dict shape now) and its module-level docstring:

```python
"""Compute auditable, type-aware prominence scores. Does not assign
visibility_tier -- that field is frozen; see ONTOLOGY.md's "Ranking and
sizing" section. Browsing/ranking uses pipeline/period_hierarchy.py's
top_entities() instead, scoped to whatever part of the tree is in view."""
```

Update `main()`:

```python
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Require and use the existing sitelink cache")
    args = parser.parse_args()
    result = compute(offline=args.offline)
    print(f"Scored {result['scored']} records (visibility_tier untouched)")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m unittest tests.test_compute_prominence -v`
Expected: all pass, including `test_visibility_tier_is_left_untouched`.

- [ ] **Step 5: Run the full suite; do NOT run `compute_prominence.py` against the real dataset**

Run: `.venv/Scripts/python.exe -m unittest discover -s tests -v` — all green.
Run: `.venv/Scripts/python.exe build.py` — unaffected, counts unchanged.

Deliberately skip running `python -m pipeline.compute_prominence` against the live 4,671-file dataset as part of this task. It would rewrite every file's `prominence_score`/`prominence_components` (mostly a no-op content-wise, since the scoring math is unchanged) purely to exercise the new code path — the same "touches all 4,671 files for a mechanical run" concern already avoided earlier in this project's history. The test suite's fixture-based coverage is enough to verify the change; a full-dataset refresh is a separate, deliberate decision for whoever wants updated scores later, not a byproduct of this task.

- [ ] **Step 6: Commit**

```bash
git add pipeline/compute_prominence.py tests/test_compute_prominence.py
git commit -m "compute_prominence: remove competitive balanced_visibility algorithm

visibility_tier is now frozen at its last-computed value; visibility_override
remains the live promotion mechanism. Browsing/ranking moves to
pipeline/period_hierarchy.py's top_entities(), scoped to whatever part of the
tree is in view instead of a cross-dataset quota pass. See ONTOLOGY.md's
'Ranking and sizing' section."
```

---

## Task 9: Historical region, derived from present-day country

**Files:**
- Modify: `schema.py` — `Geography.historical_regions`/`primary_historical_region`
- Create: `pipeline/historical_regions.py` — curated ISO-country → historical-region lookup table
- Create: `pipeline/derive_historical_regions.py` — applies the table to `polities/*.yaml` and `periods/*.yaml`
- Create: `tests/test_historical_regions.py`, `tests/test_derive_historical_regions.py`
- Create (script output): `reports/historical_region_coverage.md`

**Interfaces:**
- Produces: `Geography.historical_regions: list[str]` / `primary_historical_region: str | None` — same shape as the existing `continents`/`primary_continent` pair, deliberately, so nothing that already reads `Geography` needs new branching logic to find this
- Produces: `historical_region_for_country(iso_code: str) -> str | None`
- Produces: `derive(polities_dir, periods_dir) -> dict[str, int]` (coverage counts)

This closes the gap flagged in `ONTOLOGY.md` ("What this doesn't replace") — a spatial classification finer than continent (West Asia vs. the Sahel vs. the Andes vs. Mesoamerica vs. Southeast Asia), independent of the `Period` tree per the "Tree, lanes, graph" section. Measured before writing this: `geography.present_countries` is populated on 2,992 of 4,671 polities (64%) — a solid base for a lookup-table derivation, better coverage than `continents` had before the August geography backfill.

- [ ] **Step 1: Write the failing test for the lookup table**

Create `tests/test_historical_regions.py`:

```python
import unittest

from pipeline.historical_regions import HISTORICAL_REGIONS, historical_region_for_country


class HistoricalRegionForCountryTests(unittest.TestCase):
    def test_known_country_resolves(self) -> None:
        self.assertEqual(historical_region_for_country("IR"), "west_asia")
        self.assertEqual(historical_region_for_country("PE"), "andes")
        self.assertEqual(historical_region_for_country("MX"), "mesoamerica")

    def test_unknown_country_returns_none(self) -> None:
        self.assertIsNone(historical_region_for_country("ZZ"))

    def test_every_country_code_maps_to_exactly_one_region(self) -> None:
        seen: dict[str, str] = {}
        for region_id, countries in HISTORICAL_REGIONS.items():
            for country in countries:
                self.assertNotIn(
                    country, seen, f"{country} assigned to both {seen.get(country)} and {region_id}"
                )
                seen[country] = region_id


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_historical_regions -v`
Expected: `ImportError`.

- [ ] **Step 3: Write the lookup table**

Create `pipeline/historical_regions.py`:

```python
"""Curated ISO alpha-2 country -> historical region lookup. A starter set,
not exhaustive -- a country missing from this table falls back to continent
in derive_historical_regions.py, same "cheap default, grow the table later"
pattern as every other reference list in this project. Region ids are not
Period.tier citizens (see ONTOLOGY.md's "Tree, lanes, graph" section) --
this is a standalone spatial classification, referenced by geography.
"""

from __future__ import annotations

HISTORICAL_REGIONS: dict[str, list[str]] = {
    "west_asia": ["IR", "IQ", "TR", "SY", "JO", "LB", "IL", "PS", "SA", "YE",
                  "OM", "AE", "QA", "BH", "KW", "CY", "GE", "AM", "AZ"],
    "central_asia": ["KZ", "UZ", "TM", "TJ", "KG", "AF"],
    "south_asia": ["IN", "PK", "BD", "LK", "NP", "BT", "MV"],
    "east_asia": ["CN", "JP", "KR", "KP", "MN", "TW", "HK", "MO"],
    "southeast_asia": ["ID", "MY", "TH", "VN", "PH", "MM", "KH", "LA", "SG", "BN", "TL"],
    "western_europe": ["FR", "DE", "BE", "NL", "LU", "GB", "IE", "CH", "AT", "MC", "LI"],
    "northern_europe": ["SE", "NO", "DK", "FI", "IS", "EE", "LV", "LT"],
    "southern_europe": ["IT", "ES", "PT", "GR", "MT", "SM", "VA", "AD"],
    "eastern_europe": ["RU", "UA", "BY", "PL", "CZ", "SK", "HU", "RO", "BG", "MD"],
    "balkans": ["SI", "HR", "BA", "RS", "ME", "MK", "AL", "XK"],
    "north_africa": ["EG", "LY", "TN", "DZ", "MA", "SD", "SS"],
    "horn_of_africa": ["ET", "ER", "DJ", "SO"],
    "west_africa": ["NG", "GH", "CI", "SN", "ML", "BF", "NE", "GN", "BJ", "TG",
                     "SL", "LR", "MR", "GM", "GW", "CV"],
    "central_africa": ["CD", "CG", "CM", "CF", "GA", "GQ", "TD", "AO", "ST"],
    "east_africa": ["KE", "TZ", "UG", "RW", "BI", "MW", "ZM", "MZ"],
    "southern_africa": ["ZA", "NA", "BW", "ZW", "LS", "SZ"],
    "north_america": ["US", "CA"],
    "mesoamerica": ["MX", "GT", "BZ", "HN", "SV", "NI", "CR", "PA"],
    "caribbean": ["CU", "JM", "HT", "DO", "PR", "TT", "BS", "BB"],
    "andes": ["PE", "BO", "EC", "CO"],
    "southern_cone": ["AR", "CL", "UY", "PY"],
    "brazil_amazonia": ["BR"],
    "oceania_pacific": ["AU", "NZ", "PG", "FJ", "SB", "VU", "WS", "TO"],
}


def historical_region_for_country(iso_code: str) -> str | None:
    for region_id, countries in HISTORICAL_REGIONS.items():
        if iso_code in countries:
            return region_id
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m unittest tests.test_historical_regions -v`
Expected: PASS.

- [ ] **Step 5: Add the schema fields**

In `schema.py`'s `Geography` model, mirroring `continents`/`primary_continent` exactly:

```python
    historical_regions: list[str] = Field(default_factory=list)
    primary_historical_region: str | None = None
```

Extend the existing `_primary_is_a_known_continent` validator (rename it or add a twin) so `primary_historical_region` must appear in `historical_regions`, same rule as the continent pair:

```python
    @model_validator(mode="after")
    def _primary_is_a_known_historical_region(self) -> "Geography":
        if self.primary_historical_region is not None and self.primary_historical_region not in self.historical_regions:
            raise ValueError("primary_historical_region must also appear in historical_regions")
        if self.primary_historical_region is None and len(self.historical_regions) == 1:
            self.primary_historical_region = self.historical_regions[0]
        return self
```

- [ ] **Step 6: Write the failing test for the derivation script**

Create `tests/test_derive_historical_regions.py`:

```python
import unittest

from pipeline.derive_historical_regions import region_for_document


class RegionForDocumentTests(unittest.TestCase):
    def test_derives_from_present_countries(self) -> None:
        document = {"geography": {"present_countries": ["IR", "IQ"], "continents": ["asia"]}}
        self.assertEqual(region_for_document(document), ["west_asia"])

    def test_multiple_countries_can_span_multiple_regions(self) -> None:
        document = {"geography": {"present_countries": ["FR", "DE"], "continents": ["europe"]}}
        self.assertEqual(sorted(region_for_document(document)), ["western_europe"])

    def test_falls_back_to_nothing_when_country_unmapped_and_absent(self) -> None:
        document = {"geography": {"present_countries": [], "continents": ["europe"]}}
        self.assertEqual(region_for_document(document), [])

    def test_unmapped_country_is_silently_skipped_not_an_error(self) -> None:
        document = {"geography": {"present_countries": ["AQ"], "continents": ["antarctica"]}}
        self.assertEqual(region_for_document(document), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 7: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_derive_historical_regions -v`
Expected: `ImportError`.

- [ ] **Step 8: Write the derivation script**

Create `pipeline/derive_historical_regions.py`:

```python
"""Pipeline step: derive historical_regions/primary_historical_region from
present_countries (falling back to nothing, never to continent -- continent
is much coarser and a wrong specific region is worse than an honestly-empty
one). Only fills gaps; never overwrites a manually-set value (checks
manual_overrides, same convention as enrich_geography.py)."""

from __future__ import annotations

from pathlib import Path

import yaml

from pipeline.historical_regions import historical_region_for_country

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"
PERIODS_DIR = ROOT / "periods"
REPORT_PATH = ROOT / "reports" / "historical_region_coverage.md"


def region_for_document(document: dict) -> list[str]:
    countries = (document.get("geography") or {}).get("present_countries") or []
    regions = {historical_region_for_country(c) for c in countries}
    regions.discard(None)
    return sorted(regions)


def _apply(directory: Path) -> tuple[int, int]:
    updated = 0
    total = 0
    for path in sorted(directory.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        total += 1
        if "geography" not in document:
            continue
        if "historical_region" in (document.get("manual_overrides") or []):
            continue
        if document["geography"].get("historical_regions"):
            continue
        regions = region_for_document(document)
        if not regions:
            continue
        document["geography"]["historical_regions"] = regions
        if len(regions) == 1:
            document["geography"]["primary_historical_region"] = regions[0]
        path.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        updated += 1
    return updated, total


def main() -> None:
    polity_updated, polity_total = _apply(POLITIES_DIR)
    period_updated, period_total = _apply(PERIODS_DIR)
    REPORT_PATH.write_text(
        "# Historical region coverage\n\n"
        f"- Polities updated this run: {polity_updated} / {polity_total}\n"
        f"- Periods updated this run: {period_updated} / {period_total}\n\n"
        "Derived only from present_countries via pipeline/historical_regions.py's "
        "starter lookup table (24 regions, ~110 country codes) -- records with no "
        "present_countries, or whose countries aren't in the table yet, are left "
        "unset rather than guessed. Growing the table is cheap and safe to rerun.\n",
        encoding="utf-8",
    )
    print(f"polities: {polity_updated}/{polity_total} updated; periods: {period_updated}/{period_total} updated")


if __name__ == "__main__":
    main()
```

- [ ] **Step 9: Run test, then the script**

Run: `.venv/Scripts/python.exe -m unittest tests.test_derive_historical_regions -v`
Expected: PASS.

Run: `.venv/Scripts/python.exe -m pipeline.derive_historical_regions`
Expected: prints update counts; given 2,992 polities already have `present_countries`, expect several hundred to over a thousand successfully classified depending on how well the starter table's ~110 country codes cover what's actually in the dataset (rarer/historical-only country codes won't be in the table yet — that's fine, same "starter set, grows over time" pattern).

- [ ] **Step 10: Run build and full suite**

Run: `.venv/Scripts/python.exe build.py` — counts unchanged (existing records only gained an optional field).
Run: `.venv/Scripts/python.exe -m unittest discover -s tests -v` — all green.

- [ ] **Step 11: Commit**

```bash
git add schema.py pipeline/historical_regions.py pipeline/derive_historical_regions.py tests/test_historical_regions.py tests/test_derive_historical_regions.py polities/*.yaml periods/*.yaml reports/historical_region_coverage.md
git commit -m "geography: derive historical_regions from present_countries (starter table)"
```

---

## Task 10: Wire into the Makefile, README, and PLAN.md

**Files:**
- Modify: `Makefile`
- Modify: `README.md`
- Modify: `PLAN.md`

- [ ] **Step 1: Add Makefile targets**

Add near the other pipeline targets in `Makefile`:

```makefile
seed-regional-eras:
	python -m pipeline.seed_regional_eras

generate-modern-regional-eras:
	python -m pipeline.generate_modern_regional_eras

suggest-regional-eras:
	python -m pipeline.suggest_regional_eras

suggest-period-links:
	python -m pipeline.suggest_period_links

period-hierarchy-report:
	python -m pipeline.period_hierarchy

derive-historical-regions:
	python -m pipeline.derive_historical_regions
```

Add these six names to the `.PHONY` line at the top of the file. **Remove** `compute-prominence` from the documented "Wikidata backbone" sequence in `README.md` if it's listed there as a routine step — running it is now optional (updates `prominence_score` only) rather than part of the standard pipeline.

- [ ] **Step 2: Add a status entry to PLAN.md**

Add a new row to the Phase table (after Phase 8) and a matching detail bullet:

```markdown
| 9 — Period ontology | **Foundational layer done** | `Period.tier` schema field, build-time tier/cycle validation, 9 macro chapters, 20 hand-curated + auto-generated modern regional eras, suggestion queues for regional-era and polity period-links, tested `pipeline/period_hierarchy.py` query layer (`top_entities` replaces the retired competitive visibility-tier algorithm) | Work the two suggestion queues (`reports/regional_era_suggestions.jsonl`, `reports/period_link_suggestions.jsonl`); replace auto-generated modern regional eras with hand-curated sub-continental ones over time; the timeline UI itself (separate plan) reads `pipeline/period_hierarchy.py` |
```

- [ ] **Step 3: Run full suite one last time, commit**

Run: `.venv/Scripts/python.exe -m unittest discover -s tests -v` — all green.
Run: `.venv/Scripts/python.exe build.py` — confirm final period count.

```bash
git add Makefile README.md PLAN.md
git commit -m "docs: wire period-ontology targets into Makefile, README, PLAN.md"
```

---

## Self-review

**Spec coverage** — every design point from `ONTOLOGY.md` has a task: chronological hierarchy (Tasks 1, 3, 4), build-time tier validation (Task 2), single-parent convention (Task 4's data + Task 2's validator), tier-scoped geography emptiness (Task 3's test + Task 6's documented reasoning), naming/`defines` relation convention (documented in `ONTOLOGY.md`; no code required until something actually needs it — noted, not silently dropped), retiring the competitive visibility algorithm (Task 8), scope-local ranking via `top_entities` (Task 7). Not covered here, and explicitly out of scope: the Holocene/geological display layer (UI-only, future plan) and a fine-grained historical-region field (flagged as an open gap in `ONTOLOGY.md`, not solved).

**Placeholder scan** — no TBD/"add appropriate handling" left in. Known rough edges are called out explicitly with a stated reason they're not blocking (auto-generated `source_urls` possibly not resolving in Task 4 Part A; the `min_length=1` schema relaxation needed for Task 4 Part B's placeholder rows).

**Type consistency** — `tier` values (`macro_chapter`, `regional_era`, `period` — three, not four; no separate `subperiod`) match across Tasks 1-7. `PeriodHierarchy`'s five public methods are defined once in Task 7 and used with consistent names in Task 10's Makefile comment and `ONTOLOGY.md`. `Geography.historical_regions`/`primary_historical_region` (Task 9) mirror `continents`/`primary_continent`'s exact field shape and validator pattern.

## Explicitly out of scope

- The actual timeline UI (`web/`, `server/`), including any parallel-lane rendering — computed at render time from data this plan already produces, not a data-layer task.
- The Holocene/geological-epoch display layer — a static UI asset, not a `Period`-tree citizen (see `ONTOLOGY.md`).
- Exhaustive country coverage in `pipeline/historical_regions.py`'s lookup table (Task 9 ships a ~110-country starter set; the remaining countries fall back to unset, not a wrong guess) — growing it is cheap, incremental, future work.
- Working the two review queues to completion — ongoing curation, same as Seshat/consolidation/type-eligibility.
- Hand-curated sub-continental regional eras for 1500-present — Task 4 Part B's auto-generated continent-level nodes are a placeholder for this.
- Refining `weight_by_era` via a better multi-source pipeline — per `ONTOLOGY.md`, this becomes ordinary editorial curation, not a pipeline investment.
