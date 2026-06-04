.PHONY: verify lint-imports build up down logs test

# tests/ is .dockerignore'd (not baked into the image) and the backend runs
# read_only, so mount tests at runtime and keep pytest's cache out of the RO fs.
PYTEST_RUN = docker compose run --rm --no-deps \
	-e PYTHONDONTWRITEBYTECODE=1 \
	-v "$(CURDIR)/tests:/app/tests:ro" \
	backend pytest tests/ -p no:cacheprovider

verify: lint-imports
	@echo "=== Running security invariant tests ==="
	$(PYTEST_RUN) -v --tb=short
	@echo "=== Checking for known CVEs ==="
	@# HARD gate (was `|| true`, which silently passed when pip-audit was absent).
	@# Self-bootstrap pip-audit into a cached venv so the check has no host prereq.
	@python3 -m venv .audit-venv >/dev/null 2>&1 || true
	@.audit-venv/bin/pip install -q --disable-pip-version-check pip-audit
	.audit-venv/bin/pip-audit -r requirements.txt --progress-spinner off
	@echo "=== Import direction check ==="
	python3 tools/check_imports.py
	@echo "=== All checks passed ==="

lint-imports:
	python3 tools/check_imports.py

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f backend

test:
	$(PYTEST_RUN) -v --tb=short -x
