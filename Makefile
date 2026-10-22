.PHONY: dev test ingest reset

dev:
	uvicorn api.main:app --reload

test:
	pytest -q tests/

ingest:
	python -m ingest.sections
	python -m ingest.mappings
	python -m ingest.cases

reset:
	python -m ingest.sections
	python -m ingest.mappings
	python -m ingest.cases
