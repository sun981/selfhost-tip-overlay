.PHONY: setup verify lint-imports build up down logs test scan

# Container-image CVE scan (OS layer — the gap pip-audit can't see: nginx/cloudflared/
# python base). Runs trivy via its official image so there's no host prereq (mirrors the
# self-bootstrapped pip-audit gate). --ignore-unfixed: only fail on CVEs that HAVE a fix,
# so an unpatchable upstream base CVE can't wedge the gate red forever (per the pip-audit
# `|| true` lesson in CLAUDE.md — don't weaken a gate, scope it). Kept OUT of `verify` so
# the inner dev loop stays fast/offline; run in CI or before a release.
# .trivyignore carries scoped, justified exceptions (upstream-image lag for CVEs off our
# path); mounted in so the gate still fails on any NEW finding.
TRIVY_RUN = docker run --rm -v trivy-cache:/root/.cache/ \
	-v "$(CURDIR)/.trivyignore:/.trivyignore:ro" aquasec/trivy:latest \
	image --ignore-unfixed --ignorefile /.trivyignore \
	--severity HIGH,CRITICAL --exit-code 1 --no-progress

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

# KEEP IN SYNC: these pins must mirror Dockerfile.backend (python) and
# docker-compose.yml (nginx, cloudflared) — a stale pin here means the gate
# scans an image we no longer ship (drift caught 2026-06-10).
scan:
	@echo "=== Scanning container images for fixable HIGH/CRITICAL CVEs ==="
	$(TRIVY_RUN) python:3.14.5-slim@sha256:c845af9399020c7e562969a13689e929074a10fd057acd1b1fad06a2fb068e97
	$(TRIVY_RUN) nginx:1.30.2-alpine@sha256:5f979dcfed4ce6461873f087e8c980d6e29b084b9e8776d9704a7e989b5f4898
	$(TRIVY_RUN) cloudflare/cloudflared:2026.6.0@sha256:ba461b8aa9c042156dbd39c38657fe7431bafa063220eab8d5330a523863da9f
	@echo "=== Image scan clean (no fixable HIGH/CRITICAL) ==="

lint-imports:
	python3 tools/check_imports.py

# First-time setup wizard — guided .env + secure token + OBS URL (macOS/Linux).
# On macOS you can also just double-click setup.command instead.
setup:
	bash scripts/setup.sh

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
