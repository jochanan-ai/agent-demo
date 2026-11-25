# The site is plain static files; the only Python here is the optional local server and the tests.
# `make test` is what CI runs too (.github/scripts/asome_ci.sh test), including the coverage report.
PYTHON ?= python3
VENV   ?= .venv
REPORT ?= build

.PHONY: test check serve install clean

install: $(VENV)/bin/python

$(VENV)/bin/python: requirements-dev.lock
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --quiet --require-hashes -r requirements-dev.lock

test:
	@PY=""; \
	if [ -x "$(VENV)/bin/python" ]; then PY="$(VENV)/bin/python"; \
	elif $(PYTHON) -c "import pytest" >/dev/null 2>&1; then PY="$(PYTHON)"; \
	else $(MAKE) --no-print-directory install && PY="$(VENV)/bin/python"; fi; \
	[ -n "$$PY" ] || { echo "no pytest available and the hash-locked install failed" >&2; exit 1; }; \
	echo "tests with coverage: $$PY"; \
	mkdir -p $(REPORT) && \
	$$PY .github/scripts/pycov.py --junit $(REPORT)/junit.xml --json $(REPORT)/coverage.json -- -q

# syntax check of the page's own script (and of the harness) — no build step, node only validates
check:
	@command -v node >/dev/null 2>&1 || { echo "node not installed: skipped"; exit 0; }; \
	node --check assets/js/main.js && node --check tests/js/run.mjs && node --check tests/js/dom.mjs

serve:
	$(PYTHON) -m site_serve

clean:
	rm -rf $(REPORT) $(VENV)
