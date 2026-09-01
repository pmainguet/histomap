# Histomap

A data-driven recreation of the 1931 Sparks/Rand McNally *Histomap*: a horizontal timeline showing
the relative weight of polities through history. The durable artifact is the validated YAML
dataset in `polities/`; the web view and future print poster are generated from it.

**Audience:** the author (43, history-literate) and family, including a child who will grow into
it over years. Hobby project, long-lived, good data.

**Core principle:** automate extraction from open historical datasets, reconcile with LLM-assisted
review, hand-curate only what genuinely needs human judgment.

See [STATUS.md](STATUS.md) for current implementation status, phase-by-phase build narrative, and
dataset metrics; [ROADMAP.md](ROADMAP.md) for remaining work and open design questions; and
[ONTOLOGY.md](ONTOLOGY.md) for the chronological (macro chapter → regional era → period → polity →
event), documentary-status (prehistory/history), and geographic classification the dataset is
organized around — read it before adding new period or navigation structure. Its rollout is
tracked in [docs/plans/2026-08-29-period-ontology.md](docs/plans/2026-08-29-period-ontology.md).

## Quickstart

Create and activate a virtual environment, then install the project:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Validate the canonical records and generate `data.json`:

```powershell
make build
```

Serve the workspace at <http://127.0.0.1:8000/>:

```powershell
make serve
```

`/` redirects to `/explore`, the primary workspace — a browsable hierarchy (macro chapters,
regional eras, and periods as stacked bands, with a toggleable polities band and civilizations/
cultures lane), with side-panel editing for reclassifying and correcting records directly. It
reads a separate, gitignored build artifact (`explore_tree.json`), so it needs at least one
`make build` (or the equivalent below) to have run before it has anything to show; `make serve`
already does this for you since it depends on `build`. The editorial review workspaces
(consolidation, entity-type, subdivision-parent) are at <http://127.0.0.1:8000/reviews>. The
Seshat-matching review page was retired 31 August 2026 once its queue emptied out
(`pipeline/reconcile.py` and `pipeline/apply_review_decisions.py` stay as scripts/API hooks for
whenever new source data needs reconciling again — see ROADMAP.md). The server binds only to
localhost and exposes a fixed allowlist of pipeline actions.

## Windows without `make`

`make` isn't available by default on Windows. Run the same actions with the venv's Python
directly (`py = .\.venv\Scripts\python.exe`):

```powershell
$py = ".\.venv\Scripts\python.exe"

& $py build.py                            # make validate
& $py -m pipeline.rebuild_timeline        # make build
& $py -m pipeline.rebuild_timeline; & $py -m server.app   # make serve (build + serve)
& $py -m unittest discover -s tests -v    # make test
ruff format .; ruff check --fix .         # make format
ruff check .; & $py -m mypy .             # make lint
```

`make serve`'s Makefile target depends on `build`, so it always rebuilds first — running
`$py -m server.app` on its own **skips that rebuild**. If you've started the server directly
without the `rebuild_timeline` step first, pages that read a build artifact (`data.json`,
`explore_tree.json`, ...) will 404 or show stale data until you run a build and restart.

## Wikidata backbone

One-shot data-import/enrichment sequence -- these steps built the initial dataset and are rerun
only for a fresh import or a full re-enrichment pass, not part of the day-to-day `make` targets
(`setup`/`validate`/`build`/`serve`/`test`/`format`/`lint`/`check`; see the Makefile). Run directly
(`$py = .\.venv\Scripts\python.exe`):

```powershell
& $py pipeline/extract_wikidata.py
& $py -m pipeline.audit_civilizations
& $py pipeline/extract_seshat.py
& $py pipeline/extract_maddison.py
& $py pipeline/map_maddison.py
& $py pipeline/extract_hyde.py
& $py pipeline/filter_wikidata_types.py
& $py pipeline/wd_to_yaml.py
& $py pipeline/reconcile.py
& $py pipeline/review_cli.py
& $py pipeline/spotcheck.py
& $py pipeline/compute_prominence.py   # updates prominence_score only; visibility_tier is frozen
& $py pipeline/compute_weights.py
& $py pipeline/enrich_relationships.py
& $py pipeline/enrich_geography.py
& $py build.py
```

Raw downloads and generated `data.json` are gitignored. Existing canonical YAML files are
preserved during import unless `pipeline/wd_to_yaml.py --overwrite` is explicitly requested.
Direct Wikidata types are classified as accepted, excluded, or review before import; the rules
live in `pipeline/wikidata_types.toml` and ambiguous entities remain visible only in Full dataset.
The prominence stage keeps every record and (re)computes `prominence_score`, but no longer assigns
`visibility_tier` — that field is frozen and only changes via a manual `visibility_override`.
Browsing/ranking now happens through `pipeline/period_hierarchy.py`'s `top_entities()`, scoped to
wherever in the tree you're browsing (see ONTOLOGY.md's "Ranking and sizing" section); the web view
defaults to the compact global tier.

---

## Consolidation review: how `suggested_decision` works

The `/reviews/consolidation` workspace pairs each pending entity with candidate matches and, where
the evidence is clear enough, proposes one of six outcomes: **same entity**, **phase_of** (the
reviewed entity is a bounded phase of the candidate — e.g. "Syrian Arab Republic" is a phase of
"Syria"), **candidate_phase_of** (the reverse direction — the candidate is a phase of the reviewed
entity), **part_of** / **candidate_part_of** (a subdivision relationship, not a time-bounded phase
— e.g. New Zealand is part of the Realm of New Zealand), or **independent** (no real relationship).
When the evidence doesn't clearly point one way, it proposes nothing and leaves it to manual
review. The logic lives in `consolidation_review_queue()` in `server/app.py`, with regression
coverage for every case below in `tests/test_consolidation_suggestions.py`.

### The signals

- **Same Wikidata ID** — the two records point to the identical Wikidata item. The strongest
  possible signal.
- **Exact name match** — one record's canonical name (or an alias/translation) matches the
  other's exactly, after stripping trailing disambiguators like "(1920–1952)".
- **"X of Y" naming pattern ("regime_of")** — e.g. "Kingdom of Hungary" reads as a regime *of*
  Hungary. Only counts toward phase_of if the regime side also has a finite end date — otherwise
  it's read as an open question rather than a completed phase, since a still-ongoing entity that
  merely matches the naming pattern (e.g. "Realm of New Zealand") is often actually a *broader*
  container rather than a phase.
- **Direct Wikidata relationship** — a real "part of" (P361) or successor (P155/P156) claim
  between the two specific Wikidata items, not just a shared parent.
- **Dates nest exactly** — one record's date range sits entirely inside the other's, with no
  tolerance for estimate noise: a boundary that misses by even one year does not count. Both sides
  being open-ended ("present") counts as nesting; a side that has already ended cannot contain a
  side that's still open.
- **Geography overlaps** — the two share at least one present-day country. Missing geography data
  on *both* sides is treated as unknown, not a match — it is never used to satisfy this check on
  its own. But when only one side has no `present_countries` recorded while the other does (a
  phase record that never got its own geography populated, e.g. "Republic of Georgia
  (1990–1992)" vs. "Georgia"), that's not a conflict either — a phase reasonably shares its
  matched entity's location, so it's treated as compatible. A genuine conflict (both sides have
  data and it doesn't overlap) is tracked separately and still blocks the match. Roughly a third
  of the dataset has no `present_countries` recorded at all, so pairs where *neither* side has any
  geography still need a real name/Wikidata signal to surface a suggestion.
- **Coordinate conflict** — the two are centered over 1,500km apart, which rules out a same-entity
  or phase relationship even if names/dates otherwise look close.
- **Identical dates, different names, different Wikidata IDs ("likely siblings")** — e.g. two
  cantons that split from one parent on the same date. Read as independent, not one being a phase
  of the other.
- **Same alias, no date overlap, different Wikidata IDs** — a name reused for an unrelated later
  era (e.g. "Kingdom of France" reused by the Bourbon Restoration). Read as independent.
- **Same Wikidata ID but wildly different dates** — flags a likely data error (misattributed QID)
  rather than trusting it as a real match; suggests nothing so a human looks at it.

### The priority order

1. **Suspicious QID reuse** → suggest nothing (flag for a human).
2. **Same Wikidata ID** → same entity.
3. **Documented successor / coordinate conflict / alias-reuse / likely-siblings** → independent.
4. **Dates nest one way, with a name match (exact, "X of Y", or a direct Wikidata relationship)** →
   phase_of. No finite end is required on either side — the backend approximates a missing end
   date rather than refusing the decision, so the suggestion isn't more conservative than the
   backend it feeds. The one case that would need protecting against (an "X of Y"-named but
   still-open, broader container mistaken for a completed phase) is already covered by the naming
   pattern's own finite-end requirement above.
5. **Dates nest the other way, same conditions** → candidate_phase_of.
6. **Direct Wikidata "part of" relationship alone, without date nesting** → part_of /
   candidate_part_of.
7. **None of the above fired, and there's no name/Wikidata signal at all** → independent (the pair
   only reached the queue via weak token/geography/date matching).
8. Otherwise → suggest nothing.

---

## Approach summary

Build a layered pipeline that extracts from multiple open sources, reconciles disagreements via an LLM-assisted review queue, computes visual weights from territory/population/complexity rather than hand-assigning them, and produces both an interactive web view and a print-ready poster from a single canonical dataset.

The dataset itself — YAML files in a Git repo — is the long-term artifact. Everything else (viz, print, reading levels) is regenerable from it.

### Why not full manual curation
Slow, doesn't scale, can't be re-tuned.

### Why not full automation
Sources disagree. Wikidata's pre-1000 CE quality is poor. Splits/merges and iconography need human judgment.

### Why this hybrid
~95% of the data work is done by scripts. The human (you) makes ~500 accept/edit/skip decisions in a review UI — one evening's work — and a smaller number of editorial decisions on transitions and icons. Result: good data, minimal manual entry, fully reproducible.

---

## Data sources

| Source | Role | Format | Notes |
|---|---|---|---|
| **Wikidata** (SPARQL) | Entity backbone, ~3,000 polities | Live query → Parquet | Inconsistent quality, especially pre-1000 CE |
| **Seshat / Cliopatria** | Authoritative dates, territory, complexity | CSV / GeoJSON | ~600 polities, ~35 regions only |
| **Maddison Project** | Population + GDP, year 1 CE → today | Excel/CSV | Modern nation-state framing |
| **HYDE 3.5** | Gridded population, 10,000 BCE → 2025 | NetCDF | Geographic — aggregate by polity territory |
| **CShapes 2.0** | Modern state boundaries 1886 → today | Shapefile | Modern only |
| **World Historical Gazetteer** | Place-name reconciliation | API | Helps join datasets |

---

## Architecture

```
┌─ Wikidata SPARQL ─┐
│   ~3,000 polities │──┐
└───────────────────┘  │
                       ▼
┌─ Seshat / Cliopatria┐  ┌──────────────────────┐    ┌────────────────┐
│   ~600 polities     │─▶│  Reconciler (Python) │───▶│ candidates.db  │
│   authoritative     │  │  fuzzy name + date   │    │ + conflicts    │
└─────────────────────┘  │  matching            │    └────────────────┘
                         └──────────────────────┘             │
┌─ Maddison + HYDE ──┐                                        │
│   pop, GDP, area   │───────────────────────────────────────▶│
└────────────────────┘                                        ▼
                                                    ┌────────────────────┐
                                                    │  LLM review queue  │
                                                    │  proposes merged   │
                                                    │  records           │
                                                    └────────────────────┘
                                                            │
                                                            ▼
                                                    ┌────────────────────┐
                                                    │  Web review UI     │
                                                    │ accept/reject/defer│
                                                    │  ~5s per polity    │
                                                    └────────────────────┘
                                                            │
                                                            ▼
                                                    ┌────────────────────┐
                                                    │  polities/*.yaml   │
                                                    │  canonical data    │
                                                    └────────────────────┘
                                                            │
                                                            ▼
                                                ┌──────────────────────────┐
                                                │  build.py → data.json    │
                                                │  → web viz + print PDF   │
                                                └──────────────────────────┘
```

---

## Repository structure

```
histomap/
├── sources/                    # raw downloads, gitignored
│   ├── wikidata.parquet
│   ├── seshat_polities.csv
│   ├── maddison.xlsx
│   └── hyde/
├── pipeline/
│   ├── extract_wikidata.py     # SPARQL → Parquet
│   ├── extract_seshat.py
│   ├── extract_maddison.py
│   ├── extract_hyde.py
│   ├── enrich_relationships.py # parent/successor/group candidates
│   ├── enrich_geography.py     # continent + present-country location
│   ├── reconcile.py            # fuzzy match + LLM proposals
│   ├── compute_weights.py      # area + pop + complexity → weight_by_era
│   └── review_cli.py           # terminal-based accept/edit/skip
├── polities/                   # canonical YAML, committed
│   ├── achaemenid_empire.yaml
│   └── ...
├── transitions.yaml            # manual splits/merges
├── icons/                      # SVG icons for top ~50 polities
├── schema.py                   # Pydantic validation
├── build.py                    # YAML → data.json
├── web/                        # static site (Observable Plot or D3)
└── print/                      # poster export pipeline
```

---

## Schema (one YAML file per polity)

```yaml
id: achaemenid_empire             # stable, owned by us
canonical_name: Achaemenid Empire
names:
  fr: Empire achéménide
  fa: شاهنشاهی هخامنشی
external_ids:
  wikidata: Q47222
  wikipedia_en: https://en.wikipedia.org/wiki/Achaemenid_Empire
  seshat: IrAchae
parent: median_empire             # what it succeeded
successors: [macedonian_empire]
geography:
  continents: [asia]
  present_countries: [IR, IQ, TR]
  centroid: {lat: 32.4, lon: 53.7}
  confidence: medium
start: -550
end: -330
start_confidence: medium          # high | medium | low | legendary
end_confidence: high
weight_by_era:                    # sparse; interpolate between
  -540: 4
  -500: 8
  -480: 9
  -400: 7
  -350: 5
weight_imputed: false             # true if computed from regional average
icon: persian_lion
text:
  short_child_en: "The first big Persian empire. Alexander the Great defeated it."
  short_adult_en: "Persian empire founded by Cyrus II, stretching from the Indus to Thrace."
  long_en: ""                     # written later
notes: "Wikidata 550 BCE; Seshat 559 BCE (Cyrus's accession)."
sources:
  - wikidata
  - seshat
  - maddison
```

Validated by `schema.py` (Pydantic). Anything failing schema is rejected at commit time.

This sketch originally had `region`/`culture_group` fields (as shown above); removed
from `schema.py` on 2026-08-29 — never populated at scale (>99% null), and their
intended purpose (a fine-grained historical-region classification, "Persia" rather than
just "asia") is superseded by `Geography.historical_regions` — see `ONTOLOGY.md`.

---

## What stays manual (and is fine)

Three things need human judgment regardless of automation:

1. **Splits and merges** — ~50 transition decisions for the whole project.
2. **Iconography** — pick icons for the top ~50 polities; leave the rest unlabeled.
3. **Reading-level text polish** — skim and tweak LLM output for the top ~50.

Total ongoing manual time after Phase 5: a few hours per year.

---

## Why this scales

Every Phase produces something complete and useful. None blocks the next.

| Now (MVP) | Later (if desired) |
|---|---|
| YAML in Git | Same files indexed into DuckDB |
| Python scripts | Same scripts, more sources |
| Vanilla SVG timeline | Richer SVG/canvas interaction if scale requires it |
| FastAPI serving static UI + review API | Authenticated deployment or read-only static mirror |
| Print to PDF from browser | Dedicated SVG export with `paged.js` |

The data model is the durable asset. Everything else is regenerable.

---

## Stack

- **Python 3.12** for the pipeline (`pandas`, `pydantic`, `SPARQLWrapper`, `rapidfuzz`, `pyyaml`, `xarray` for HYDE NetCDF).
- **ChatGPT API** for LLM-assisted reconciliation.
- **SQLite / DuckDB** as a working store during reconciliation (throwaway).
- **YAML files in Git** as the canonical dataset.
- **Vanilla SVG + JavaScript** for the current web visualization; no framework dependency.
- **FastAPI + Uvicorn** for one local timeline, review, and allowlisted pipeline-action server.
- **`paged.js` or headless Chromium** for print PDF export.

No Postgres or external queue is needed: YAML and JSONL remain the durable stores, and the small
FastAPI application runs on the laptop. Public write access is deferred until authentication is
implemented.
