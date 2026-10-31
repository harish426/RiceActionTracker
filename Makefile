.PHONY: setup test lint run check notify
PY=.venv/bin/python

setup:            ## create venv and install everything
	python3 -m venv .venv && .venv/bin/pip install -e '.[dev,gcp]'

test:             ## run the full automated test suite (offline)
	$(PY) -m pytest

lint:
	.venv/bin/ruff check src tests

run:              ## one tracking pass over all enabled sources
	.venv/bin/tracker run

notify:           ## test Telegram / email delivery
	.venv/bin/tracker test-notify

check: lint test
