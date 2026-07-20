# Histomap

A data-driven recreation of the 1931 Sparks/Rand McNally *Histomap*: a vertical timeline showing
the relative weight of polities through history. The durable artifact is the validated YAML
dataset in `polities/`; the web view and future print poster are generated from it.

See [PLAN.md](PLAN.md) for the complete data-source and implementation roadmap.

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

Serve the timeline at <http://localhost:8000/web/>:

```powershell
make serve
```

## Wikidata backbone

```powershell
make extract
make extract-seshat
make extract-maddison
make map-maddison
make extract-hyde
make filter-wikidata-types
make import-wikidata
make reconcile
make spotcheck
make compute-prominence
make enrich-relationships
make enrich-geography
make validate
```

Raw downloads and generated `data.json` are gitignored. Existing canonical YAML files are
preserved during import unless `pipeline/wd_to_yaml.py --overwrite` is explicitly requested.
Direct Wikidata types are classified as accepted, excluded, or review before import; the rules
live in `pipeline/wikidata_types.toml` and ambiguous entities remain visible only in Full dataset.
The prominence stage keeps every record but assigns `global`, `regional`, or `detailed` visibility;
the web view defaults to the compact global tier.
