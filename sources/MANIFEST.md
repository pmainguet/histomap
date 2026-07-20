# Source manifest

Raw source files are intentionally gitignored. This manifest records the inputs needed to
reproduce the canonical dataset.

| Source | Retrieved | Endpoint/version | Local output |
|---|---|---|---|
| Wikidata Query Service | 2026-07-19 | `https://query.wikidata.org/sparql` live data | `wikidata_raw/*.json`, `wikidata.parquet` |
| Natural Earth Admin 0 Countries | 2026-07-20 | 1:110m GeoJSON, Natural Earth master dataset | `ne_110m_admin_0_countries.geojson` |
| Seshat Equinox 2020 | 2026-07-20 | `Equinox_on_GitHub_June9_2022.xlsx` from `seshatdb/Equinox_Data` | `seshat_equinox_2022.xlsx` |

## Wikidata extraction

The Phase 1 import queried these class hierarchies:

- empire (`Q48349`)
- kingdom (`Q417175`)
- civilization (`Q8432`)
- state (`Q7275`)
- historical country (`Q3024240`)

Run `make extract` to refresh the cached raw responses and aggregate Parquet. Delete a specific
file under `sources/wikidata_raw/` or pass `--force` to deliberately refresh cached responses.
The 2026-07-19 run produced 9,251 unique QIDs, retained 5,000 non-null inception bindings, and
the YAML converter rejected 207 bindings whose inception value was not a parseable year.

## Geography boundaries

`pipeline/enrich_geography.py` caches Natural Earth's Admin 0 country boundaries from the
project's canonical `natural-earth-vector` repository. The boundaries represent present-day,
small-scale cartographic country coverage and are used only for centroid fallback assignment;
they are not historical polity boundaries.

## Seshat Equinox

The archived Equinox workbook is the current reproducible public snapshot linked from Seshat's
data page. The repository contains a CC0 license file, while its README and the current Seshat
download page describe the data as CC BY-NC-SA; Histomap conservatively treats the workbook as
CC BY-NC-SA. The live Seshat download service requires an account and acceptance of current terms.
