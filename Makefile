.PHONY: help setup import-data dev docker-build docker-run clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Set up development environment
	python -m venv .venv
	.venv\Scripts\pip install -r requirements.txt
	@echo "✅ Environment ready. Run: .venv\Scripts\activate"

import-data: ## Import player data from transfermarkt JSONs into SQLite
	python -m src.scripts.import_players

dev: ## Start development server (backend + frontend)
	python -m uvicorn src.backend.main:app --reload --port 8000

docker-build: ## Build Docker image
	docker build -t wc-fantasy .

docker-run: ## Run Docker container
	docker run -p 8000:8000 wc-fantasy

clean: ## Clean generated files and database
	del /s /q *.pyc 2>nul || true
	rd /s /q __pycache__ 2>nul || true
	del data\wc_fantasy.db 2>nul || true
