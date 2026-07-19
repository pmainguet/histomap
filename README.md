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
make import-wikidata
make compute-prominence
make validate
```

Raw downloads and generated `data.json` are gitignored. Existing canonical YAML files are
preserved during import unless `pipeline/wd_to_yaml.py --overwrite` is explicitly requested.
The prominence stage keeps every record but assigns `global`, `regional`, or `detailed` visibility;
the web view defaults to the compact global tier.
