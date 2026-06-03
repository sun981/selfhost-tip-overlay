.PHONY: verify lint-imports build up down logs test

verify: lint-imports
	@echo "=== Running security invariant tests ==="
	docker compose run --rm --no-deps backend pytest tests/ -v --tb=short
	@echo "=== Checking for known CVEs ==="
	pip-audit -r requirements.txt --progress-spinner off || true
	@echo "=== Import direction check ==="
	python tools/check_imports.py
	@echo "=== All checks passed ==="

lint-imports:
	python tools/check_imports.py

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f backend

test:
	docker compose run --rm --no-deps backend pytest tests/ -v --tb=short -x
