.PHONY: dev test ingest

dev:
	uvicorn api.main:app --reload

test:
	pytest -q tests/

ingest:
	python -m ingest.sections
