# agent-demo: `make test` is what the agent sandbox and CI run (dependencies only with hashes).
VENV := .venv
PY := $(VENV)/bin/python

.PHONY: test deps run
$(PY): requirements-dev.lock
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --quiet --require-hashes -r requirements-dev.lock
	touch $(PY)

deps: $(PY)

test: deps
	$(PY) -m pytest -q

run:
	python3 -m app.server
