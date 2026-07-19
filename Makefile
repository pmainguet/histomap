.PHONY: setup extract import-wikidata compute-prominence validate build serve test format lint check

setup:
	uv pip install -r requirements.txt ruff mypy

extract:
	python pipeline/extract_wikidata.py

import-wikidata:
	python pipeline/wd_to_yaml.py

compute-prominence:
	python pipeline/compute_prominence.py

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
