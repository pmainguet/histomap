.PHONY: setup validate build serve test format lint check

setup:
	uv pip install -r requirements.txt ruff mypy

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
