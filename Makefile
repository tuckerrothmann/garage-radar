.PHONY: help env doctor db-up db-down db-shell install migrate seed api scheduler frontend test lint clean scrape-bat scrape-cb ingest-bat ingest-cb ingest-ebay ingest-pcarmarket ingest-dry

help:
	@echo ""
	@echo "  Garage Radar make targets"
	@echo ""
	@echo "  Dev setup:"
	@echo "    make env              Create .env from .env.example"
	@echo "    make doctor           Check local prerequisites"
	@echo "    make db-up            Start Postgres via Docker"
	@echo "    make db-down          Stop Postgres"
	@echo "    make install          Create backend venv and install deps"
	@echo "    make migrate          Run Alembic migrations"
	@echo "    make seed             Seed canonical reference data"
	@echo ""
	@echo "  Run:"
	@echo "    make api              Start FastAPI"
	@echo "    make scheduler        Start the scheduler worker"
	@echo "    make frontend         Start the Next.js dev server"
	@echo "    make scrape-bat       Run BaT ingestion once (--limit 20)"
	@echo "    make scrape-cb        Run C&B ingestion once (--limit 20)"
	@echo "    make ingest-bat       Full BaT ingest (LIMIT=N to cap)"
	@echo "    make ingest-cb        Full C&B ingest (LIMIT=N to cap)"
	@echo "    make ingest-ebay      Full eBay ingest (LIMIT=N to cap)"
	@echo "    make ingest-pcarmarket Full PCA Market ingest (LIMIT=N to cap)"
	@echo "    make ingest-dry       Dry-run ingest (SOURCE=bat LIMIT=5)"
	@echo ""
	@echo "  Quality:"
	@echo "    make test             Run pytest"
	@echo "    make lint             Run Ruff"
	@echo ""
	@echo "  Cross-platform:"
	@echo "    python scripts/dev.py <command>"
	@echo ""

env:
	python scripts/dev.py env

doctor:
	python scripts/dev.py doctor

db-up:
	python scripts/dev.py compose up -d db

db-down:
	python scripts/dev.py compose stop db

db-shell:
	python scripts/dev.py compose exec db psql -U postgres -d garage_radar

install:
	python scripts/dev.py install

migrate:
	python scripts/dev.py migrate

seed:
	python scripts/dev.py seed

api:
	python scripts/dev.py api

scheduler:
	python scripts/dev.py scheduler

frontend:
	python scripts/dev.py frontend dev

scrape-bat:
	python scripts/dev.py ingest --source bat --limit 20

scrape-cb:
	python scripts/dev.py ingest --source carsandbids --limit 20

ingest-bat:
	python scripts/dev.py ingest --source bat --limit $(or $(LIMIT),50)

ingest-cb:
	python scripts/dev.py ingest --source carsandbids --limit $(or $(LIMIT),50)

ingest-ebay:
	python scripts/dev.py ingest --source ebay --limit $(or $(LIMIT),50)

ingest-pcarmarket:
	python scripts/dev.py ingest --source pcarmarket --limit $(or $(LIMIT),50)

ingest-dry:
	python scripts/dev.py ingest --source $(or $(SOURCE),bat) --limit $(or $(LIMIT),5) --dry-run

test:
	python scripts/dev.py test

lint:
	python scripts/dev.py lint

clean:
	python scripts/dev.py clean
