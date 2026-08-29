# Histomap

A data-driven recreation of the 1931 Sparks/Rand McNally *Histomap*: a vertical timeline showing
the relative weight of polities through history. The durable artifact is the validated YAML
dataset in `polities/`; the web view and future print poster are generated from it.

See [PLAN.md](PLAN.md) for the complete data-source and implementation roadmap, and
[ONTOLOGY.md](ONTOLOGY.md) for the chronological/documentary/geographic classification
system the dataset (and any future timeline UI) is organized around.

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

Serve the timeline and review workspace at <http://127.0.0.1:8000/>:

```powershell
make serve
```

The review page is available at <http://127.0.0.1:8000/review>. The server binds only to
localhost and exposes a fixed allowlist of pipeline actions.

## Windows without `make`

`make` isn't available by default on Windows. Run the same actions with the venv's Python
directly (`py = .\.venv\Scripts\python.exe`):

```powershell
$py = ".\.venv\Scripts\python.exe"

& $py build.py                            # make validate
& $py -m pipeline.rebuild_timeline        # make build
& $py -m server.app                       # make serve (build + serve)
& $py -m unittest discover -s tests -v    # make test
ruff format .; ruff check --fix .         # make format
ruff check .; & $py -m mypy .             # make lint
```

## Wikidata backbone

```powershell
make extract
make audit-civilizations
make extract-seshat
make extract-maddison
make map-maddison
make extract-hyde
make filter-wikidata-types
make import-wikidata
make reconcile
make review
make spotcheck
make compute-prominence
make compute-weights
make enrich-relationships
make enrich-geography
make validate
```

The same sequence without `make` (`$py = .\.venv\Scripts\python.exe`):

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
& $py pipeline/compute_prominence.py
& $py pipeline/compute_weights.py
& $py pipeline/enrich_relationships.py
& $py pipeline/enrich_geography.py
& $py build.py
```

Raw downloads and generated `data.json` are gitignored. Existing canonical YAML files are
preserved during import unless `pipeline/wd_to_yaml.py --overwrite` is explicitly requested.
Direct Wikidata types are classified as accepted, excluded, or review before import; the rules
live in `pipeline/wikidata_types.toml` and ambiguous entities remain visible only in Full dataset.
The prominence stage keeps every record but assigns `global`, `regional`, or `detailed` visibility;
the web view defaults to the compact global tier.
