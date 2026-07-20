# Histomap — Plan

A modern, data-driven recreation of the 1931 Sparks/Rand McNally *Histomap*: a vertical timeline showing the relative weight of polities through history.

**Audience:** the author (43, history-literate) and family, including a child who will grow into it over years. Hobby project, long-lived, good data.

**Core principle:** automate extraction from open historical datasets, reconcile with LLM-assisted review, hand-curate only what genuinely needs human judgment. 

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
                                                    │  Review CLI        │
                                                    │  accept/edit/skip  │
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
  seshat: IrAchae
parent: median_empire             # what it succeeded
successors: [macedonian_empire]
region: persia                     # displayed as "Historical grouping"
culture_group: iranian
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

---

## Implementation steps

### Phase 0 — Foundations

Setup, schema, smoke test. Goal: a validated YAML file you can build the rest of the pipeline on.

1. **Repo & environment.** Create `histomap/`, `git init`, add `.gitignore` for `sources/`, `__pycache__/`, `.venv/`, `*.parquet`, `*.duckdb`, `data.json`. Python 3.12 virtualenv. Pin `requirements.txt`:
   ```
   pandas>=2.2  pydantic>=2.7  SPARQLWrapper>=2.0  rapidfuzz>=3.9
   pyyaml>=6.0  xarray>=2024.5  netCDF4  openpyxl  unidecode
   ```
   Add a `justfile` (or Makefile) with `extract`, `reconcile`, `compute-weights`, `build`, `validate`, `serve` targets so the pipeline is one command end-to-end.

2. **Schema.** Write `schema.py` with the Pydantic model above. Enums for `*_confidence` (`high|medium|low|legendary`) and `culture_group`. Validators:
   - `end > start` (allow `end = None` for still-extant polities).
   - `weight_by_era` keys are integers (negative = BCE), values in `[1, 10]`.
   - `external_ids.wikidata` matches `^Q\d+$`.
   - `id` is `snake_case`, unique across the dataset.
   - `start` / `end` within `[-10000, 2100]`.
   Add `just validate` that loads every file in `polities/` and fails on any error; wire it into a pre-commit hook so bad YAML never lands.

3. **Smoke test.** Hand-write `polities/rome_republic.yaml` with every field populated and realistic values. Run validation. Then write a 20-line `build.py` stub that loads the directory and emits `data.json`. Confirm round-trip works.

**Done when:** `just validate && just build` succeeds on a one-file dataset and produces a JSON blob you can `jq` into.

### Phase 1 — Wikidata backbone

Get ~3,000 polities into draft YAML and render them. Quality is bad on purpose — the point is end-to-end flow before adding quality.

4. **SPARQL extraction.** `pipeline/extract_wikidata.py` runs one query per class, using `wdt:P31/wdt:P279*` to catch subclasses. Starter set of classes: state (Q7275), empire (Q48349), kingdom (Q417175), civilization (Q3024240), plus former country (verify the current QID against Wikidata before locking it in). For each entity, pull:
   - labels (`en`, `fr`, native), aliases
   - `P571` inception, `P576` dissolution (with qualifiers — Wikidata often has multiple inception dates)
   - `P2046` area, `P1082` population (capture point-in-time qualifier where present)
   - `P17` country, coordinates, `P18` image
   - all classes the entity matched (for debugging coverage)
   Paginate with `LIMIT 5000 OFFSET …`; the WDQS times out on the unioned query. Cache responses to `sources/wikidata_raw/<class>.json` so reruns are free and the upstream version is auditable. Final output: `sources/wikidata.parquet` indexed by QID.

5. **Dedup.** Group by QID. When an entity matches multiple classes (Roman Empire is both `empire` and `state`), keep one row and stash the class list in a `wd_classes` column. Drop entries with no inception year — that filters out modern administrative junk and stub items. Log dropped counts per class.

5a. **Direct-type eligibility filter.** The broad `wdt:P31/wdt:P279*` class traversal is useful for discovery but leaks cities, administrative regions, archaeological sites, fictional states, and organizations into the polity set. Fetch and retain every entity's direct `P31` (`instance of`) values, then classify records before YAML generation:
   - Exclude cities, towns, settlements, archaeological sites, buildings/fortresses, organizations, fictional entities, and modern first-/second-level administrative subdivisions.
   - Do not infer eligibility from the English label: names such as “Mexico” may denote a valid sovereign country, while “Athens” may refer to the modern city rather than the historical polity.
   - Permit genuine sovereign city-states and historical poleis only when a direct type or authoritative source supports political independence. Prefer a distinct historical entity such as Classical Athens over reusing the modern-city item.
   - Put ambiguous mixed-type records into `reports/type_review_queue.jsonl` with their direct types, dates, and matched broad classes; never silently discard them.
   - Maintain versioned allow/deny type lists in `pipeline/wikidata_types.toml`. Manual per-QID overrides handle exceptional entities without weakening the global rules.

   Emit type-filter counts and representative examples for each decision (`accepted`, `excluded`, `review`). Regression spot checks must include Mexico (`Q96`, accepted as a country), Mexico City (`Q1489`, excluded), modern Athens (`Q1524`, excluded), and an accepted reviewed historical polis/city-state.

6. **Auto-convert to YAML.** `pipeline/wd_to_yaml.py` maps each eligible Wikidata row to one draft file:
   - `id = slugify(label_en)`, suffix with last 4 of QID on collision.
   - `start = year(P571)`, `start_confidence: low`. Same for `end`.
   - `weight_by_era: {start: 5}` placeholder, `weight_imputed: true`.
   - `external_ids.wikidata = QID`. Everything else: empty.
   Commit the generated files as one bulk commit titled `wd: initial import` so future hand-edits show clearly in `git log`.

7. **Crappy streamgraph.** Minimal Observable Plot view in `web/`: years on Y axis (BCE→CE top-to-bottom), polities as horizontal bands, fixed width = 1, colored by `culture_group` or class. No labels, no transitions, no hover. The point is to *see* where coverage is thin. Expect the Bronze Age near-empty, the 19th century dense, the post-1945 explosion of nation-states obvious.

7a. **Prominence and visibility tiers.** Keep the complete canonical dataset, but prevent obscure entities and administrative subdivisions from overwhelming the default chart. `pipeline/compute_prominence.py` combines Wikidata sitelink reach, longevity, authoritative-source coverage, editorial work, and a parent-country penalty for still-extant entities. (For extinct polities, Wikidata's country field often means present-day location rather than political subordination.) It writes a reproducible `prominence_score` and one of three display tiers:
   - `global`: the few hundred polities suitable for a world-history overview.
   - `regional`: important regional polities, visible when the reader asks for more detail.
   - `detailed`: the full research dataset, including minor and disputed entities.

   Thresholds are global and deterministic, but the renderer may additionally cap active bands per region/century to prevent well-documented regions from crowding out others. Manual editorial text, icons, and Seshat coverage can promote a polity; no automated score deletes canonical data.

7b. **Political relationships and display groups.** `pipeline/enrich_relationships.py` extracts Wikidata relationship candidates using `P361` (part of), reciprocal `P527` (has part), `P17` (country), `P155`/`P156` (follows/followed by), and `P1365`/`P1366` (replaces/replaced by). Keep three concepts separate:
   - `parent`: accepted political containment, used when one polity was genuinely subordinate to or contained by another.
   - `successors`: chronological continuity, splits, and replacements.
   - `group`: an editorial display umbrella such as Roman polities, Chinese dynasties, or the British Empire; groups may collapse into one band in the global view and expand in regional/detail views.

   Never treat `P17` or `P131` as automatic political ancestry: for historical entities they often describe present-day location or modern administration. Score candidates using reciprocal statements, date compatibility, and source agreement. Auto-accept only strong reciprocal matches; retain the Wikidata property, confidence, and evidence for weaker candidates and send them to the Phase 4 review queue. Relationship cycles and impossible date ordering fail validation.

7c. **Geographic enrichment.** `pipeline/enrich_geography.py` assigns at least a continent and one or more present-day countries to every polity where evidence permits. The canonical geography block stores `continents`, ISO 3166-1 alpha-2 `present_countries`, an optional centroid, and `confidence`.
   - Prefer historical polygons from Cliopatria/Seshat and intersect them with Natural Earth modern-country polygons; this supports polities spanning several current countries.
   - Until polygons are available, use Wikidata coordinates (`P625`) and reverse-map the point into a modern country and continent.
   - Treat Wikidata `P17` and `P131` only as fallback candidates, because their meaning is inconsistent for extinct polities.
   - Keep multi-continent and multi-country results rather than forcing one location. Preserve the evidence and mark centroid-only or inferred assignments as low/medium confidence.

   Emit a coverage report by century and visibility tier. Missing geography remains explicit rather than being guessed. The web view uses these fields for continent/country filters and, later, a linked map.

**Done when:** the streamgraph renders all imported polities at the selected visibility tier; strong parent/successor relationships can be grouped or expanded; and the geography report shows continent and present-country coverage, with unknowns visible for Phase 2 to improve.

### Phase 2 — Authoritative overlay

Reconcile Seshat and the territorial atlas data into the Wikidata draft set. After this, the pre-1500 picture should be markedly less embarrassing.

8. **Download sources.** Seshat: bulk export from the public databank (CSV per equinox dataset). Cliopatria / chronological atlas data: GeoJSON polygons + metadata. Drop everything into `sources/` (gitignored). Record exact dataset version and download date in `sources/MANIFEST.md` — this is the only thing that makes the pipeline reproducible later.

9. **Normalize Seshat.** `pipeline/extract_seshat.py` produces a flat table: `(polity_id, start_year, end_year, area_km², population, social_complexity_index, nga, polity_alt_names)`. Seshat encodes dates as text (`"c. 550 BCE"`, `"early 4th century CE"`); write an explicit date parser with rules for `c.`, BCE/CE, century language, and date ranges. Ambiguous parses: keep the row, set `start_confidence: medium` and stash the raw string in `notes`.

10. **Reconcile.** `pipeline/reconcile.py`:
    - **Name normalization:** lowercase, strip diacritics (`unidecode`), drop `{Empire, Kingdom, Dynasty, Caliphate, the, of}`, transliterate non-Latin.
    - **Name score:** `rapidfuzz.WRatio` on normalized names, also matching against Wikidata aliases (not just primary label).
    - **Date overlap:** Jaccard of the (start, end) year intervals.
    - **Auto-accept** when `name_score ≥ 90` AND `date_overlap ≥ 0.5`. Upgrade both `*_confidence` to `high`, pull in Seshat territory + complexity, append Seshat ID to `external_ids`.
    - **Soft match** when `70 ≤ name_score < 90` OR `date_overlap < 0.5`: emit to `reports/review_queue.jsonl` with both source rows for Phase 4 LLM triage.
    - **Seshat-only:** entries with no Wikidata candidate become new draft YAMLs (`notes: "Seshat-only"`, no Wikidata external_id).
    - Emit `reports/reconcile_summary.md` with counts per century: auto-accepted / queued / unmatched. This is the dashboard for whether the phase worked.

11. **Re-render.** Same streamgraph as Phase 1, now colored by `start_confidence` (high = solid, low = hatched/translucent). Spot-check 10 well-known polities spanning eras — Akkad, Achaemenid, Han, Sasanian, Abbasid, Song, Mongol, Ottoman, Mughal, Qing — by clicking through to verify dates and territory. If those look right, the matching logic is correct enough to continue.
    The reproducible baseline lives in `pipeline/spotcheck.py` and writes `reports/phase2_spotcheck.md`; incomplete source and present-country coverage remains visible as warnings.

**Done when:** the reconcile report shows ≥ 60% of Seshat polities auto-matched, the confidence overlay shows pre-1500 CE noticeably less murky than after Phase 1, and the 10 spot-checks pass without obvious wrongness.

### Phase 3 — Weight computation

Compute `weight_by_era` from territory, population, and complexity. The output is what makes the streamgraph *honest* about scale — Han Dynasty should dwarf Lan Xang.

12. Download Maddison Project (`mpd2023_web.xlsx`, ~5 MB) and the HYDE 3.5 baseline
population-count NetCDF (~640 MB compressed). Add both to `sources/MANIFEST.md` with version.
HYDE downloads are slow and rate-limited — do it once and cache aggressively.

13. `pipeline/extract_maddison.py`: long-format table `(country, year, population, gdp_per_capita)`. Country codes are modern ISO — map to our polity IDs only for 1500+ entities; pre-modern populations fall back to HYDE.
    The extractor targets the official MPD 2023 workbook, detects its data sheet/header, converts
    population from thousands to persons, and emits `sources/maddison.parquet` plus a coverage report.
    `pipeline/map_maddison.py` initially joins only accepted, extant post-1500 polities directly
    typed by Wikidata as countries/sovereign states and having exactly one present-day country;
    historical and multi-country entities wait for polygon-based allocation.

14. `pipeline/extract_hyde.py`: load with `xarray`, aggregate gridded population to polity territory. **Catch:** we only have polygons for the Seshat-covered ~600 polities. For everyone else, fall back to the polity's NGA centroid + a regional radius, or use the modern successor's footprint as a crude proxy. Mark these with `weight_imputed: true`. Persist `sources/pop_by_polity.parquet` keyed by `(polity_id, year)`.
    The first implementation reads population-count NetCDF grids and emits explicitly imputed
    centroid-radius estimates; polygon aggregation remains the next accuracy upgrade.

15. `pipeline/compute_weights.py`:
    ```
    raw(polity, year) =
        0.4 · log10(area_km² + 1)
      + 0.4 · log10(population + 1)
      + 0.2 · normalized_complexity
    weight(polity, year) = clip(10 · raw / p95(raw_in_century), 1, 10)
    ```
    Persist sparse `weight_by_era` at 50-year resolution where data exists; linear interpolation fills the gaps at render time. Any polity with one or more missing components gets `weight_imputed: true`.
    The initial implementation prefers Maddison for mapped modern states, otherwise uses HYDE,
    interpolates Seshat area/complexity, and median-imputes missing components by century. Extant
    sovereign microstates absent from Maddison retain neutral placeholders rather than misleading
    centroid-radius totals. All current computed records remain marked imputed until polygon coverage
    replaces the HYDE radius fallback.

16. **Tunable.** All coefficients, the per-century normalization, and the imputation fallbacks live in `pipeline/weights.toml`. Re-tuning is one file edit + `just compute-weights` — the canonical YAMLs are rewritten in-place, the diff lands in git for review.

**Done when:** spot-checked band widths reflect actual scale (Han ≈ Roman ≈ heavy, one-city kingdoms thin), and a sensible perturbation to `weights.toml` (e.g., raise the area coefficient) shifts the streamgraph the way you'd expect.

### Phase 4 — LLM review queue
15. Estimate the workload/price of doing this step entirely. We don't want to have something too costly
15 bis. Write `pipeline/llm_propose.py`: for each candidate polity, send the merged source rows to the ChatGPT API, get back a structured proposal with conflict notes and child/adult reading-level text.
16. Write `pipeline/review_cli.py`: terminal UI that walks proposals, shows diff vs. existing YAML, accepts with Enter, edits in `$EDITOR`, skips with `s`.
17. Run the review. Budget: 5s per polity × ~500 polities = ~40 minutes. Expect to spend longer on disputed dates.

### Phase 5 — Manual editorial pass
18. Create `transitions.yaml` for non-trivial splits/merges (Roman fragmentation, Mongol partitions, decolonization). ~50 entries total.
19. Draw or source SVG icons for the top ~50 polities into `icons/`.
20. Tighten short-child text for the top ~50; the LLM's first pass is usable but uneven.

### Phase 6 — Web view
21. Write `build.py`: YAML files → single `data.json` (compact, indexed by era).
22. Build the streamgraph in `web/`:
    - Vertical timeline, horizontal stream width, splits/merges from `transitions.yaml`.
    - Reading-level toggle (child / adult).
    - Historical-grouping, continent, present-country, and visibility-tier filters; era zoom and hover cards.
    - Collapsible display groups derived from reviewed political relationships.
    - Linked geographic map once historical polygon coverage is sufficient.
    - Confidence shown as opacity or hatching.
23. Host on Cloudflare Pages (free, static).

### Phase 7 — Print poster
24. Write `print/render.py`: master SVG at A1/A0 dimensions, vector text, embedded legend and methodology footer.
25. Export PDF via headless Chromium or `paged.js`.
26. Print at local shop. Frame.

### Phase 8 — Grow with the kid
- Fill `long_en` text for top polities over time. Doing this together is part of the project.
- Add reading levels 2 and 3 (ages 9–12 / teen) as additional text fields.
- Add regional zoom views, language toggles, family-history band at the bottom, map integration if interest holds.
- **Nice-to-have relationship navigation:** make parent, children, predecessors, and successors clickable in the detail card; add breadcrumbs, related-band highlighting, and a small tree centered on the selected polity. Later, allow scrolling to a related band and expanding/collapsing descendants or reviewed display groups. This is intentionally deferred until relationship review has improved the underlying links.
- **Nice-to-have geographic/relationship layout:** replace alphabetical band order with a stable hierarchy of continent → present-day country → reviewed relationship/display group. Within a geographic block, keep parents, children, predecessors, and successors adjacent where possible, then use prominence and chronology as deterministic tie-breakers. Multi-country or multi-continent polities should appear once in a clearly defined primary block, with visual links or cross-references from their other regions rather than duplicated bands. Unknown geography gets an explicit final block. Preserve an optional alphabetical order for lookup and debugging. This layout is deferred until geography coverage and relationship review are reliable enough that automated grouping will not mislead readers.

---

## What stays manual (and is fine)

Three things need human judgment regardless of automation:

1. **Splits and merges** — ~50 transition decisions for the whole project.
2. **Iconography** — pick icons for the top ~50 polities; leave the rest unlabeled.
3. **Reading-level text polish** — skim and tweak LLM output for the top ~50.

Total ongoing manual time after Phase 5: a few hours per year.

---

## Honest scope warnings

- **Wikidata quality drops off a cliff before ~1000 CE.** Automated pipeline gives ~60% accuracy for ancient history, ~95% for modern. The visual tolerates this; don't expect Bronze Age polities to be as crisp as the 19th century.
- **Seshat is sparse.** It covers ~35 Natural Geographic Areas, not the whole world. Regions outside Seshat coverage rely on Wikidata only and stay at `confidence: low`.
- **Pre-3000 BCE is mostly archaeological cultures, not polities.** Represent them as broad bands ("Bronze Age Mesopotamia"), not as crisp entities.
- **Source disagreements are normal.** Keep them in the `notes` field rather than pretending they don't exist. The `*_confidence` fields are the right place to surface this in the viz.

---

## Why this scales

Every Phase produces something complete and useful. None blocks the next.

| Now (MVP) | Later (if desired) |
|---|---|
| YAML in Git | Same files indexed into DuckDB |
| Python scripts | Same scripts, more sources |
| Observable Plot streamgraph | D3 with split/merge animations |
| Static HTML on Cloudflare Pages | Same, with API if needed |
| Print to PDF from browser | Dedicated SVG export with `paged.js` |

The data model is the durable asset. Everything else is regenerable.

---

## Stack

- **Python 3.12** for the pipeline (`pandas`, `pydantic`, `SPARQLWrapper`, `rapidfuzz`, `pyyaml`, `xarray` for HYDE NetCDF).
- **ChatGPT API** for LLM-assisted reconciliation.
- **SQLite / DuckDB** as a working store during reconciliation (throwaway).
- **YAML files in Git** as the canonical dataset.
- **Observable Plot** (or D3 later) for the web viz.
- **Static HTML on Cloudflare Pages** for hosting.
- **`paged.js` or headless Chromium** for print PDF export.

No Postgres, no FastAPI, no backend, no infrastructure. The whole project runs on a laptop.
