# Histomap — Period Ontology and Information Architecture

This is the authoritative definition of the dataset's chronological and documentary
classification. It is a living reference, not a dated plan — keep it in sync with
`schema.py` whenever the ontology changes. The implementation history for how this
was rolled out into the dataset lives in
[`docs/plans/2026-08-29-period-ontology.md`](docs/plans/2026-08-29-period-ontology.md);
this document is that plan's spec, and outlives it.

## Why this exists

The dataset (4,671 polities, 117+ periods, sourced from Wikidata/Seshat/Maddison/HYDE)
is detailed but was never designed to be *navigated* — there's no notion of "zoom out to
see the whole of human history, then zoom in." Two mistakes to avoid when adding one:

1. **Don't make "prehistorical → protohistorical → historical" a chronological axis.**
   It looks like a timeline but it's really "how much written evidence do we have,"
   which happened at wildly different times in different societies. Treating it as a
   universal sequence of eras misrepresents the actual history.
2. **Don't make "Bronze Age" / "Medieval" / "Classical antiquity" the top of the
   hierarchy.** These are real, useful period *names*, but each is regional and
   time-bounded in a specific tradition (there's no "global Bronze Age" with one start
   date) — they belong one or two layers below a genuinely global navigation spine.

## The four classification axes

Keep these separate. A record's position on one axis says nothing about its position
on another.

| Axis | Values | Where it lives |
|---|---|---|
| **Chronological hierarchy** | macro chapter → regional era → period → subperiod → polity → event | `Period.tier` + `Period.broader_periods` chain; `Polity` and `Transition` (unchanged) |
| **Documentary status** | `prehistory` \| `history` | `Period.documentary_status` / `Polity.documentary_status` (derived, see below) |
| **Geography** | continent → (region, in future) | `Geography.continents` / `primary_continent` (existing field, unchanged) |
| **Date certainty** | `high` \| `medium` \| `low` \| `legendary` | `Confidence` on `start_confidence`/`end_confidence` (existing field, unchanged) |

Documentary status is never the parent of a period in the chronological hierarchy, and
a chronological tier never implies a documentary status. "Early Cities and States"
(a macro chapter) contains societies on both sides of the prehistory/history line at
the same time — that's expected, not a modeling error.

### Documentary status is derived, not asserted directly

Primary navigation stays binary (`prehistory`/`history`), but the actual evidence is
recorded first, and the binary is computed from it — so nuance survives as metadata
instead of forcing a lossy up-front judgment call:

| `evidence_basis` | meaning | implied `documentary_status` |
|---|---|---|
| `archaeological_only` | no writing, or none usable, for this society/place | `prehistory` |
| `external_written` | known only through outside observers' written accounts (e.g. the Celts, mostly known via Greek/Roman writers) | `history` |
| `local_written` | the society's own (even if sparse/undeciphered-in-part) written record | `history` |
| `mixed` | both local and external written evidence | `history` |

A record can set `documentary_status` explicitly instead of relying on the derivation,
but not to a value that contradicts its own `evidence_basis` — that's a validation
error, not a silent override.

## The chronological hierarchy

| Tier | Meaning | Stored as | Example |
|---|---|---|---|
| 0. Human past | Root; implicit, not a record | — | — |
| 1. **Macro chapter** | Global navigation spine, editorial, not a claim of simultaneity | `Period`, `tier: macro_chapter` | Classical and Imperial Worlds |
| 2. **Regional era** | One tradition's broad periodization within one region | `Period`, `tier: regional_era` | Mediterranean Classical Antiquity |
| 3/4. **Period / subperiod** | A recognized interval, possibly nested via `broader_periods` | `Period`, `tier: period` (default) | Viking Age; Roman Republic-era Mediterranean |
| 5. **Phase, reign, polity** | A political actor with a lifespan | `Polity` (unchanged model) | Roman Republic |
| 6. **Event** | A dated occurrence | `Transition` (unchanged model) | — |

Two design choices that keep this additive to the existing schema rather than a parallel
structure:

- **Tiers 1-4 are all just `Period` records at different `tier` values, chained via the
  existing `broader_periods` field.** No new foreign-key fields, no new file type. Every
  one of the 117 pre-existing period files defaults to `tier: period` and needs no edits.
- **Entities (polities) are never nested inside a period.** They link *into* the
  hierarchy via the existing `period_links.yaml` (`period_id` + `entity_id` +
  `relation`), same mechanism already used for e.g. `house_of_tudor_period → phase_of →
  kingdom_of_england`. "Akkadian Empire" is a polity with a lifespan; "Old Babylonian
  period" is a period; the polity links to the period, it does not become a child of it.

A period MAY skip a tier and link straight to a coarser one — e.g. a period with no
regional era authored yet can point `broader_periods` straight at its macro chapter.
Sparse-but-correct beats forcing a fake intermediate node.

## The 9 macro chapters (fixed, global)

These are the top of the hierarchy — the "World" zoom level. Dates are approximate,
overlap deliberately at their boundaries, and are an editorial navigation spine, not a
claim that every society moved in lockstep.

| id | Name | Span |
|---|---|---|
| `macro_human_origins_paleolithic` | Human Origins and Paleolithic Worlds | −3,000,000 to −10,000 |
| `macro_agricultural_transitions` | Agricultural Transitions and Settled Societies | −10,000 to −3,500 |
| `macro_early_cities_states` | Early Cities and States | −3,500 to −1,200 |
| `macro_classical_imperial_worlds` | Classical and Imperial Worlds | −1,200 to 500 |
| `macro_postclassical_worlds` | Post-Classical Worlds | 500 to 1,500 |
| `macro_early_modern_connections` | Early Modern Global Connections | 1,500 to 1,800 |
| `macro_industrial_imperial_world` | Industrial and Imperial World | 1,800 to 1,914 |
| `macro_world_wars_reordering` | World Wars and Global Reordering | 1,914 to 1,945 |
| `macro_contemporary_world` | Contemporary World | 1,945 to present |

Named "Post-Classical" rather than "Medieval" deliberately — "medieval" describes
Latin Christendom, not the Byzantine, Islamic, African, South Asian, or East Asian
worlds occupying the same centuries.

This list is meant to be stable. Changing it means renumbering every regional era's
`broader_periods` pointer — treat it the way you'd treat a database migration, not a
routine edit.

## Regional eras (growing set, starts at 20)

One tier below the macro chapters — this is where "Bronze Age Europe" and "Bronze Age
China" become two different, comparable nodes instead of one overloaded label. Each
regional era belongs to exactly one macro chapter and one or more continents.

The starter set (see the implementation plan for the full authored list) covers macro
chapters 1-5 (deep past through ~1500 CE) across Africa, Asia, Europe, North America,
and South America — the window where a single global label genuinely misrepresents
different regions' actual trajectories. From 1500 onward, `geography.primary_continent`
(already populated on 72% of polities) plays this role for now; the sheer volume of
Wikidata-derived modern nation-states makes bespoke sub-continental regional eras
(Latin America, Southeast Asia, colonial Sub-Saharan Africa, ...) a real but separate
future addition, added the same way: one YAML file, `broader_periods` pointing at its
macro chapter, geography continents set.

## What this replaces

- `Period.kind` (`historical | archaeological | protohistorical | prehistorical`) —
  superseded for navigation by `documentary_status`/`evidence_basis`. Not deleted:
  117 existing records already carry it, and it costs nothing to leave as a legacy
  field. New records should prefer `documentary_status`/`evidence_basis`.
- `Polity.region` / `Polity.culture_group` — these were meant to be the "historical
  grouping" layer per the original schema sketch in `PLAN.md`, but were never populated
  at scale (null on 4,521/4,671 and 4,670/4,671 records respectively as of 2026-08-29).
  The regional-era tier supersedes their intended purpose. Left in place, unused,
  rather than removed for zero functional gain.

## How a future timeline UI should read this

Query through `pipeline/period_hierarchy.py`, not by re-deriving `broader_periods` or
`period_links.yaml` traversal in the UI layer:

- `macro_chapters()` — the 9 ids, in order → the "World" zoom level.
- `children(period_id)` → what to show one zoom level in.
- `entities_under(period_id)` → every polity transitively under a node, for whatever
  zoom level is currently showing polities rather than sub-periods.
- `ancestors(period_id)` → breadcrumb trail back to the macro chapter, for a "Record"
  view that wants to show where it sits in the hierarchy.
