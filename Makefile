.PHONY: help setup test lint serve-frontend serve-backend fetch-players fetch-scores clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Set up development environment
	python -m venv .venv
	.venv/Scripts/activate && pip install -r requirements.txt
	@echo "✅ Environment ready. Run: .venv/Scripts/activate"

test: ## Run all tests
	python -m pytest tests/ -v

lint: ## Run linting
	python -m ruff check src/

serve-frontend: ## Serve frontend with live reload (VS Code Live Server recommended)
	@echo "Open src/frontend/index.html with Live Server in VS Code"
	@echo "Or run: python -m http.server 8080 --directory src/frontend"

serve-backend: ## Start FastAPI backend
	cd src/backend && python -m uvicorn main:app --reload --port 8000

fetch-players: ## Update player data from Transfermarkt
	python src/scripts/fetch_players.py --all

fetch-scores: ## Fetch latest match scores
	python src/scripts/fetch_scores.py

clean: ## Clean generated files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache
