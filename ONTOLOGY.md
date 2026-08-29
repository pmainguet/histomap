# Histomap — Period Ontology and Information Architecture

This is the authoritative definition of the dataset's chronological classification.

## Why this exists

The dataset (4,671 polities, 117+ periods, sourced from Wikidata/Seshat/Maddison/HYDE)
is detailed but was never designed to be *navigated* — there's no notion of "zoom out to
see the whole of human history, then zoom in." The mistake to avoid when adding one:
**don't make "Bronze Age" / "Medieval" / "Classical antiquity" the top of the
hierarchy.** These are real, useful period *names*, but each is regional and
time-bounded in a specific tradition (there's no "global Bronze Age" with one start
date) — they belong one or two layers below a genuinely global navigation spine.

Two axes considered and rejected here, for the same underlying reason (don't let a
classification that varies by society become a level of a supposedly-universal tree):

- **Prehistory/History documentary status.** Would only ever have covered the 117
  `Period` records, never the 4,671 `Polity` records that make up most of what gets
  browsed — not enough payoff for the added schema complexity. `Period.kind`'s existing
  `historical`/`archaeological`/`protohistorical`/`prehistorical` values are untouched
  and remain the dataset's only evidentiary classification; it is not deprecated, since
  nothing here replaces it.
- **Geological chronology (Quaternary/Pleistocene/Holocene/Greenlandian/Northgrippian/
  Meghalayan).** Structurally this is correct as a *parallel* axis — the Holocene alone
  spans 8 of the 9 macro chapters, so nesting it inside the human-history tree would
  repeat the same mistake as the documentary-status one. Per your steer, this is a
  **display-alongside layer, not a `Period`-tree citizen** — it doesn't belong in
  `periods/*.yaml` at all, since it isn't something entities link to and it isn't
  editorially placed the way a regional era is; it's a fixed reference band a future UI
  renders next to the human-history timeline. Treat it as a small static reference
  table (ICS boundaries: Greenlandian/Northgrippian/Meghalayan, plus Pleistocene above
  it), not part of `schema.py`'s `Period` model, with zero coupling to
  `broader_periods`/`tier`/`period_links.yaml`. Out of scope for this plan (which stops
  at the `Period`/`Polity` data layer); belongs in the future timeline-UI plan as a
  static asset it renders, the same way it'll render axis labels or a legend.

## Year numbering

Confirmed from the pipeline (`pipeline/wd_to_yaml.py`'s `parse_year()`, docstring:
"Parse a Wikidata timestamp (including astronomical BCE years)"): dates use
**astronomical year numbering**, inherited directly from Wikidata, with no proleptic
adjustment applied anywhere in the pipeline. Year 0 exists (= 1 BCE); `-27` means
"astronomical year −27," not "27 BCE" as conventionally written (which would be
astronomical −26). This was an inherited convention, not a deliberate choice, and
wasn't written down anywhere before now — stating it explicitly here so nobody
"corrects" it into an off-by-one bug later.

## The four classification axes

Keep these separate. A record's position on one axis says nothing about its position
on another.

| Axis | Values | Where it lives |
|---|---|---|
| **Chronological hierarchy** | macro chapter → regional era → named period (recursive) | `Period.tier` + `Period.broader_periods`, described below |
| **Geography** | continent → (region, in future — see "What this doesn't replace") | `Geography.continents` / `primary_continent` (existing field, unchanged) |
| **Date certainty** | `high` \| `medium` \| `low` \| `legendary` | `Confidence` on `start_confidence`/`end_confidence` (existing field, unchanged) |
| **Source provenance** | which dataset(s) attest a record | `Polity.sources` / `Period.source_urls` (existing fields, unchanged) |

## The chronological hierarchy

This is a **period hierarchy** with two separate kinds of things linked onto it — not
one flat tier list. An earlier draft of this document listed "period → subperiod →
polity → event" as if they were siblings in one sequence, which directly contradicted
its own "entities are never nested inside a period" rule. Corrected structure:

**Period hierarchy** (temporal containers only, all `Period` records):

| Tier | Meaning | `Period.tier` value | Example |
|---|---|---|---|
| 0. Human past | Root; implicit, not a record | — | — |
| 1. Macro chapter | Global navigation spine, editorial | `macro_chapter` | Classical and Imperial Worlds |
| 2. Regional era | One tradition's periodization within one region | `regional_era` | Mediterranean Classical Antiquity |
| 3+. Named period | Recursively nestable via `broader_periods`; depth is however deep the chain goes, not a fixed count | `period` (default) | Roman period → Roman Republic-era Mediterranean → Late Republic |

**Linked records** (not part of the tier chain; they attach to a period via
`period_links.yaml`):

| Layer | Stored as | Example |
|---|---|---|
| Entities | `Polity` (unchanged model) | Roman Republic (the state, with a lifespan) |
| Events | `Transition` (unchanged model) | — |

Two design choices that keep this additive to the existing schema rather than a
parallel structure:

- **Tiers 1-3+ are all just `Period` records at different `tier` values, chained via
  the existing `broader_periods` field.** No new foreign-key fields, no new file type.
  Every one of the 117 pre-existing period files defaults to `tier: period` and needs
  no edits.
- **Entities (polities) are never nested inside a period.** They link *into* the
  hierarchy via the existing `period_links.yaml` (`period_id` + `entity_id` +
  `relation`), same mechanism already used for e.g. `house_of_tudor_period → phase_of →
  kingdom_of_england`.

A period MAY skip a tier and link straight to a coarser one — e.g. a period with no
regional era authored yet can point `broader_periods` straight at its macro chapter.
Sparse-but-correct beats forcing a fake intermediate node.

### `roman_republic` vs `roman_republic_period`: naming rule for dual concepts

Some names genuinely refer to both a political entity and a conventional period (the
Roman Republic is both a state with a government, and a name historians use for an era
of Mediterranean history broader than just Rome's own government). Rule: a bare id
always refers to the `Polity` if one exists; the `Period` gets an explicit `_period`
suffix. This is already the de facto convention for every period authored under this
plan (`viking_age_period`, `house_of_tudor_period`, ...) — now written down so it holds
for future additions too. When a period and a polity describe essentially the same
span (not just an overlapping one — e.g. a `_period` record created specifically to
give a polity a browsable period-tier presence), link them via a `period_links.yaml`
entry using a new `relation: defines` value (alongside the existing `context` /
`phase_of` / `part_of_periodization`), rather than adding a dedicated schema field —
the linking mechanism already exists, this just gives it a name for this specific case.

### `broader_periods`: single parent by convention, not by schema type

The field stays typed `list[str]` (matches the existing schema — no type change), but
every period authored under this plan uses exactly one entry. This resolves two
things at once:

- **Breadcrumbs stay unambiguous.** `ancestors()` walks a single chain; there's never
  a "which parent do I show" question for the UI, because there's only ever one.
- **Date overruns don't require a second parent.** A regional era's chapter membership
  is *editorial* ("this era is characteristically part of this chapter"), not a claim
  that its `start`/`end` sits entirely inside the chapter's range — see below. An
  earlier version of this feedback proposed a `primary_broader_period` +
  `overlapping_macro_periods` split to handle exactly this case; it's not needed here,
  because none of the 20 starter regional eras actually need *two* chapter parents —
  each has one clear home, just with a date tail that runs past the boundary. If a
  genuinely dual-membership case shows up later (a region equally characteristic of two
  eras, not just spilling over one boundary), the schema already supports adding a
  second `broader_periods` entry without a migration — it's just not exercised today,
  and `ancestors()`/build-time validation (below) should keep enforcing single-parent
  until something concrete needs otherwise.

### `broader_periods` is editorial placement, not a date-range claim

**Important, and easy to get wrong:** a regional era's `broader_periods` pointer says
"this era is characteristically part of this chapter," not "this era's `start`/`end`
falls entirely inside the chapter's `start`/`end`." Real periodization overruns clean
boundaries constantly — Mesoamerican Formative/Classic civilization runs to 900 CE, a
full 400 years past the nominal 500 CE end of "Classical and Imperial Worlds," because
that's when it actually ended, not because the chapter's date range was chosen badly.

Practical consequence: `entities_under(macro_chapter_id)` returns everything
*editorially tagged* under that chapter, which is **not** the same as "everything whose
dates fall within the chapter's date range." A query like "which polities existed in
1000 BCE" should read `Polity.start`/`Polity.end` directly, not walk the period tree —
the tree is for browsing, not for exhaustive date-range indexing. Any period whose
range extends past its parent's boundary should say so in its `notes` field (the
Task 3 starter set already does this for the five rows it affects).

### Geography emptiness is tier-scoped, not ambiguous

Only `tier: macro_chapter` records may have `geography.continents: []`, and there it
means "deliberately global" (a macro chapter isn't regional by definition). Everywhere
else — `regional_era`, `period`, and every `Polity` — an empty `continents` list means
"unknown/not yet classified," same as it does today on the 1,315 polities missing
geography. Code that treats emptiness as "matches every continent" (e.g. a period-link
suggester skipping the continent filter) must check `tier` first; it is never safe to
infer "global" from emptiness alone outside the macro-chapter tier.

### Allowed parent tiers (enforced at build time, not per-record)

A per-record Pydantic validator can't check this — it needs to know the *referenced*
period's tier, which means seeing the whole dataset, same as `build.py`'s existing
`find_parent_cycles()` for polities. Rule, to be added as a `validate_period_tiers()`
build-time check alongside that:

| A period with tier... | ...must have `broader_periods` that is | Cycle check |
|---|---|---|
| `macro_chapter` | empty | — |
| `regional_era` | exactly one id, whose tier is `macro_chapter` | reject if the chain ever revisits an id |
| `period` | exactly one id, whose tier is `macro_chapter`, `regional_era`, or `period` | same |

`children()` orders results by `start` ascending — the same rule `macro_chapters()`
already uses. There's no authored "editorial order" field, and start-date order is
free; if genuine non-chronological ordering is ever needed (e.g. a thematic grouping),
that's a field to add when something actually needs it, not before.

`entities_under()` returns a deduplicated set — an entity linked at two levels, or via
two different `relation` values, appears once. It does not currently filter by
`relation` (a period_links entry of any kind — `context`, `phase_of`,
`part_of_periodization`, `defines` — counts); a relation-filtered variant (e.g. "only
direct rulership, not just context") is a reasonable future addition once a consumer
actually needs to distinguish them.

## The 9 macro chapters (fixed, global)

These are the top of the hierarchy — the "World" zoom level. Dates are an editorial
navigation spine — approximate, and not a claim that every society moved in lockstep —
but the 9 chapters themselves are contiguous with no gap or overlap (each one's `end`
equals the next one's `start` exactly); it's the regional eras and periods sitting
inside them that legitimately spill across a chapter boundary, per the note above.

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

This list is meant to be stable. Changing it means reassigning every regional era's
`broader_periods` pointer to a different id (ids are stable semantic strings, not
numeric — there's nothing to renumber, but every downstream pointer does need
reviewing) — treat it the way you'd treat a database migration, not a routine edit.

## Regional eras (two-speed authoring)

One tier below the macro chapters — this is where "Bronze Age Europe" and "Bronze Age
China" become two different, comparable nodes instead of one overloaded label. Each
regional era belongs to exactly one macro chapter (per the editorial-placement note
above) and one or more continents.

Authored two different ways, deliberately:

- **Macro chapters 1-5 (deep past through ~1500 CE): 20 hand-curated rows**, each with a
  real name and a researched date range (e.g. `mediterranean_classical_era`,
  `east_asian_bronze_age_era`) — because in this window, a continent-level label alone
  would flatten together traditions that genuinely need separate nodes.
- **Macro chapters 6-9 (1500-present): auto-generated, continent × chapter only**,
  wherever the dataset actually has polities in that combination — e.g.
  `europe_industrial_imperial_world_era`. No historical research, no bespoke naming;
  this exists purely so no zoom path dead-ends into "nothing here" for the roughly
  60% of the dataset that lands in this date range. Real sub-continental regional eras
  for this window (Latin America, Southeast Asia, colonial Sub-Saharan Africa, ...) are
  a legitimate future addition, added the hand-curated way once someone wants to invest
  the research.

## What this doesn't replace

`Polity.region` / `Polity.culture_group` were meant to be a "historical grouping"
layer per the original schema sketch in `PLAN.md`, but were never populated at scale
(null on 4,521/4,671 and 4,670/4,671 records respectively as of 2026-08-29). They stay
unpopulated and unremoved — but the regional-era tier does **not** replace their
intended purpose the way an earlier draft of this document claimed. Regional era is a
*temporal* classification ("Mediterranean Classical Antiquity" — a time window in one
tradition); `region`/`culture_group` were meant to be *spatial*/*cultural*
classifications ("Persia," "the Sahel," "Iranian") independent of time. A polity's
regional era does not tell you its historical region, any more than "Classical and
Imperial Worlds" tells you a polity is in Persia rather than Gaul.

This is a real, still-open gap: continents are too coarse for West Asia vs. the Sahel
vs. the Andes vs. Mesoamerica vs. Southeast Asia, and nothing in this plan fixes it.
Worth a dedicated historical-region field/gazetteer before authoring much more content
that depends on fine-grained place, not just continent — flagged here as future work,
not solved by anything above.

## Ranking and sizing: scope-local, not global-competitive

Two existing systems were built to answer "how important/how big is this record"
*across the entire flat dataset*, with no structure to scope by:

- `visibility_tier` (`global`/`regional`/`detailed`), assigned by
  `compute_prominence.py`'s `balanced_visibility()` — a competitive quota algorithm
  (top 60 absolute + top-2 per continent/era stratum) that recomputes across all 4,671
  records whenever it runs.
- `weight_by_era` — visual band-width weight, mostly `weight_imputed: true` today
  (per `PLAN.md`: "the large majority of records are still imputed"), computed from
  sparse Maddison/HYDE/Seshat population and area data.

Now that the ontology tree exists, "what's important here" becomes a **local** question
— within "Mediterranean Classical Antiquity," what stands out is obvious without a
cross-dataset algorithm. Going forward:

- **`compute_prominence.py`'s competitive `balanced_visibility()` pass is retired from
  routine use.** `visibility_tier` stays frozen at its current values (harmless legacy
  data). `visibility_override` remains the live mechanism for "always show this one" —
  it already is in practice: the last several promotions (Nazi Germany, the European
  Union, the "Major Civilizations & Powers" pass) all went through `visibility_override`
  directly, not a full recompute.
- **Browsing/ranking within any tree node uses `prominence_score` directly** (still
  cheaply computed per-record, no change there) via a new `top_entities(period_id,
  limit)` helper in `pipeline/period_hierarchy.py`: entities under a node, sorted by
  score, `visibility_override` pinned first. No global rebalancing needed when a new
  entity is added — see the implementation plan.
- **`weight_by_era`'s multi-source estimation pipeline (`compute_weights.py`) is not
  worth further algorithmic investment** — most values are imputed proxies already. The
  field stays (band width is core to the actual Histomap visual, not redundant with the
  ontology), but refining specific weights becomes ordinary editorial curation — the
  same review-queue pattern as everything else in this project — rather than a pipeline
  problem to solve with more source data.

## Tree, lanes, graph: three things, not one

The temptation, once a tree exists, is to make it answer every question. It shouldn't:

- **The `Period` tree answers "where am I in the curated account of history."**
  Deliberately narrow (9 macro chapters, a few dozen regional eras) — this is
  navigation, not an attempt to model everything that was ever true at a given time.
- **A future UI's parallel display lanes (by geography, by polity type, whatever)
  answer "what else was true at the same time."** These are computed at render time
  from `start`/`end`/`geography` that already exist on every record — nothing here
  persists an `overlaps` relationship, because it's cheaper and more honest to compute
  it than to store and maintain a second copy of what the dates already say.
- **The relationship graph answers "how is this connected to that, independent of
  time."** Already exists — `Polity.relationships` (`political_parent`,
  `cultural_component`, `associated_people`, `archaeological_sequence`, ...). Nothing
  to add here either.

None of the three should absorb the others. In particular: a **historical region**
("West Asia," "the Sahel," "Mesoamerica") does not belong as a tier in the `Period`
tree, even though it's tempting to slot it in between macro chapter and regional era.
A region doesn't have a `start`/`end` the way every other tree node does — forcing it
into `Period` to make it a tree level would repeat the exact mistake already avoided
twice above (documentary status, geological chronology): a non-temporal classification
becoming a level of a temporal hierarchy. It belongs in its own structure — continent →
region → subregion, referenced by (not nesting) both polities and periods, the same
relationship geography already has to everything else. Still the open gap noted above;
solving it doesn't mean growing the `Period` tree.

## How a future timeline UI should read this

Query through `pipeline/period_hierarchy.py`, not by re-deriving `broader_periods` or
`period_links.yaml` traversal, or `visibility_tier`, in the UI layer:

- `macro_chapters()` — the 9 ids, in order → the "World" zoom level.
- `children(period_id)` → what to show one zoom level in, ordered by `start`.
- `top_entities(period_id, limit)` → the N most prominent polities under a node
  (`visibility_override` pinned first, then by `prominence_score`) — what to show by
  default before the user asks to see everything.
- `entities_under(period_id)` → every polity transitively under a node, deduplicated,
  unranked — the "show all" behind `top_entities`'s default.
- `ancestors(period_id)` → single breadcrumb chain back to the macro chapter, for a
  "Record" view that wants to show where it sits in the hierarchy.
