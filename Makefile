.PHONY: help db-up db-down install migrate seed api frontend test lint clean

# Default target
help:
	@echo ""
	@echo "  Garage Radar — Make targets"
	@echo ""
	@echo "  Dev setup:"
	@echo "    make db-up       Start Postgres via Docker"
	@echo "    make db-down     Stop Postgres"
	@echo "    make install     Install backend Python deps (creates .venv)"
	@echo "    make migrate     Run Alembic migrations"
	@echo "    make seed        Bootstrap canonical reference data"
	@echo ""
	@echo "  Run:"
	@echo "    make api         Start FastAPI (uvicorn --reload)"
	@echo "    make frontend    Start Astro/Next.js dev server"
	@echo "    make scrape-bat  Run BaT scraper once (--limit 20)"
	@echo ""
	@echo "  Quality:"
	@echo "    make test        Run pytest"
	@echo "    make lint        Run ruff check"
	@echo ""
	@echo "  Cleanup:"
	@echo "    make clean       Remove .venv and __pycache__"
	@echo ""

# ── Database ─────────────────────────────────────────────────

db-up:
	docker-compose up -d db
	@echo "Postgres started. Waiting for healthy..."
	@until docker-compose exec db pg_isready -U postgres -d garage_radar > /dev/null 2>&1; do sleep 1; done
	@echo "✅ Postgres ready."

db-down:
	docker-compose stop db

db-shell:
	docker-compose exec db psql -U postgres -d garage_radar

# ── Backend setup ─────────────────────────────────────────────

install:
	cd backend && python -m venv .venv && \
	  .venv/bin/pip install --upgrade pip && \
	  .venv/bin/pip install -e ".[dev]"
	@echo "✅ Backend deps installed. Activate with: source backend/.venv/bin/activate"

migrate:
	cd backend && .venv/bin/alembic upgrade head
	@echo "✅ Migrations applied."

seed:
	cd backend && .venv/bin/python ../scripts/bootstrap_db.py
	@echo "✅ Reference data seeded."

# ── Run ──────────────────────────────────────────────────────

api:
	cd backend && .venv/bin/uvicorn garage_radar.api.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev

scrape-bat:
	cd backend && .venv/bin/python -m garage_radar.sources.bat.crawler --limit 20

scrape-cb:
	cd backend && .venv/bin/python -m garage_radar.sources.carsandbids.crawler --limit 20

# ── Quality ───────────────────────────────────────────────────

test:
	cd backend && .venv/bin/pytest tests/ -v

lint:
	cd backend && .venv/bin/ruff check garage_radar/

# ── Utilities ─────────────────────────────────────────────────

export-comps:
	cd backend && .venv/bin/python ../scripts/export_comps_csv.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/.venv
	@echo "✅ Cleaned."
