# AI Job Hunter — Makefile
# Usage: make <target>

.PHONY: setup run run-once bootstrap telegram-off test test-unit test-int
.PHONY: jobs gaps stats export profile reset-alerts lint format docker-build
.PHONY: docker-up docker-down docker-logs clean

PYTHON     := .venv/bin/python
PIP        := .venv/bin/pip
PYTEST     := .venv/bin/pytest
RUFF       := .venv/bin/ruff

# ── Setup ─────────────────────────────────────────────────────────────────────

setup:
	@bash scripts/setup.sh

install:
	$(PIP) install --quiet -r requirements.txt
	playwright install chromium --with-deps

# ── Run ───────────────────────────────────────────────────────────────────────

run:
	$(PYTHON) main.py

run-once:
	$(PYTHON) main.py --once

bootstrap:
	$(PYTHON) main.py --bootstrap-only

telegram-off:
	$(PYTHON) main.py --no-telegram

# ── Management CLI ────────────────────────────────────────────────────────────

profile:
	$(PYTHON) scripts/manage.py profile

jobs:
	$(PYTHON) scripts/manage.py jobs --n 20

gaps:
	$(PYTHON) scripts/manage.py gaps

stats:
	$(PYTHON) scripts/manage.py stats

export:
	$(PYTHON) scripts/manage.py export-jobs

reset-alerts:
	$(PYTHON) scripts/manage.py reset-alerts

# ── Tests ─────────────────────────────────────────────────────────────────────

test:
	$(PYTEST) tests/ -v --tb=short

test-unit:
	$(PYTEST) tests/unit/ -v --tb=short -m "not e2e"

test-int:
	$(PYTEST) tests/integration/ -v --tb=short

test-cov:
	$(PYTEST) tests/ --cov=app --cov-report=term-missing --cov-report=html

# ── Code quality ──────────────────────────────────────────────────────────────

lint:
	$(RUFF) check app/ tests/ main.py

format:
	$(RUFF) format app/ tests/ main.py

# ── Docker ────────────────────────────────────────────────────────────────────

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f job_hunter

docker-rebuild:
	docker compose down && docker compose up --build -d

# ── Utilities ─────────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache htmlcov .coverage

clean-data:
	@echo "WARNING: This will delete all job data and the database!"
	@read -p "Are you sure? (yes/no): " confirm && [ "$$confirm" = "yes" ] && \
		rm -f data/job_hunter.db data/faiss_index.* data/cache/naukri_session.json || \
		echo "Cancelled."

db-shell:
	sqlite3 data/job_hunter.db

help:
	@echo ""
	@echo "AI Job Hunter — Available Commands"
	@echo "─────────────────────────────────────────────"
	@echo "  make setup         First-run setup"
	@echo "  make run           Start full agent"
	@echo "  make run-once      Run one discovery cycle"
	@echo "  make bootstrap     Parse resume + build profile"
	@echo "  make telegram-off  Run without Telegram bot"
	@echo ""
	@echo "  make profile       Show user profile"
	@echo "  make jobs          Show top 20 jobs"
	@echo "  make gaps          Show skill gaps"
	@echo "  make stats         Show statistics"
	@echo "  make export        Export jobs to CSV"
	@echo ""
	@echo "  make test          Run all tests"
	@echo "  make test-unit     Run unit tests only"
	@echo "  make test-int      Run integration tests only"
	@echo "  make lint          Run ruff linter"
	@echo "  make format        Format code with ruff"
	@echo ""
	@echo "  make docker-up     Start with Docker Compose"
	@echo "  make docker-down   Stop Docker containers"
	@echo "  make docker-logs   Stream container logs"
	@echo "  make clean         Remove cache files"
	@echo ""
