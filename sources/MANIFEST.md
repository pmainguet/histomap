# Source manifest

Raw source files are intentionally gitignored. This manifest records the inputs needed to
reproduce the canonical dataset.

| Source | Retrieved | Endpoint/version | Local output |
|---|---|---|---|
| Wikidata Query Service | 2026-07-19 | `https://query.wikidata.org/sparql` live data | `wikidata_raw/*.json`, `wikidata.parquet` |
| Natural Earth Admin 0 Countries | 2026-07-20 | 1:110m GeoJSON, Natural Earth master dataset | `ne_110m_admin_0_countries.geojson` |

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
