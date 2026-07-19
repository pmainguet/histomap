# Source manifest

Raw source files are intentionally gitignored. This manifest records the inputs needed to
reproduce the canonical dataset.

| Source | Retrieved | Endpoint/version | Local output |
|---|---|---|---|
| Wikidata Query Service | 2026-07-19 | `https://query.wikidata.org/sparql` live data | `wikidata_raw/*.json`, `wikidata.parquet` |

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
