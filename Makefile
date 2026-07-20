.PHONY: setup extract extract-seshat extract-maddison filter-wikidata-types import-wikidata reconcile spotcheck compute-prominence enrich-relationships enrich-geography validate build serve test format lint check

setup:
	uv pip install -r requirements.txt ruff mypy

extract:
	python pipeline/extract_wikidata.py

extract-seshat:
	python pipeline/extract_seshat.py

extract-maddison:
	python pipeline/extract_maddison.py

filter-wikidata-types:
	python pipeline/filter_wikidata_types.py

import-wikidata:
	python pipeline/wd_to_yaml.py

reconcile:
	python pipeline/reconcile.py

spotcheck:
	python pipeline/spotcheck.py

compute-prominence:
	python pipeline/compute_prominence.py

enrich-relationships:
	python pipeline/enrich_relationships.py

enrich-geography:
	python pipeline/enrich_geography.py

validate:
	python build.py

build: validate

serve: build
	python -m http.server 8000

test:
	python -m unittest discover -s tests -v

format:
	ruff format .
	ruff check --fix .

lint:
	ruff check .
	mypy .

check: lint test validate
