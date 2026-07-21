.PHONY: setup extract audit-civilizations extract-seshat extract-maddison extract-hyde map-maddison filter-wikidata-types cache-wikidata-type-ancestors classify-entity-types import-wikidata reconcile apply-reviews spotcheck compute-prominence enrich-relationships enrich-geography enrich-missing-geography period-pilot validate build serve test format lint check

setup:
	uv pip install -r requirements.txt ruff mypy

extract:
	python pipeline/extract_wikidata.py

audit-civilizations:
	python -m pipeline.audit_civilizations

extract-seshat:
	python pipeline/extract_seshat.py

extract-maddison:
	python pipeline/extract_maddison.py

map-maddison:
	python pipeline/map_maddison.py

extract-hyde:
	python pipeline/extract_hyde.py

filter-wikidata-types:
	python pipeline/filter_wikidata_types.py

cache-wikidata-type-ancestors:
	python -m pipeline.cache_wikidata_type_ancestors

classify-entity-types:
	python -m pipeline.backfill_entity_types

import-wikidata:
	python pipeline/wd_to_yaml.py

reconcile:
	python pipeline/reconcile.py

apply-reviews:
	python -m pipeline.apply_review_decisions

review:
	python pipeline/review_cli.py

spotcheck:
	python pipeline/spotcheck.py

compute-prominence:
	python pipeline/compute_prominence.py

compute-weights:
	python pipeline/compute_weights.py

enrich-relationships:
	python pipeline/enrich_relationships.py

enrich-geography:
	python pipeline/enrich_geography.py

enrich-missing-geography:
	python pipeline/enrich_geography.py --only-missing

period-pilot: validate
	python -m pipeline.report_period_pilot

validate:
	python build.py

build:
	python -m pipeline.rebuild_timeline

serve: build
	python -m server.app

test:
	python -m unittest discover -s tests -v

format:
	ruff format .
	ruff check --fix .

lint:
	ruff check .
	mypy .

check: lint test validate
