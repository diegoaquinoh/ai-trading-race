.PHONY: help test test-backend test-frontend test-ml lint-backend lint-frontend lint-ml build-backend build-frontend

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── All ───

test: test-backend test-frontend test-ml ## Run all checks (same as CI)

# ─── Backend (.NET) ───

build-backend: ## Build backend and tests in Release mode
	dotnet build AiTradingRace.Tests/AiTradingRace.Tests.csproj --configuration Release

test-backend: build-backend ## Run backend unit tests (excludes Integration tests needing Docker)
	dotnet test AiTradingRace.Tests/AiTradingRace.Tests.csproj --configuration Release --no-build --verbosity normal --filter "Category!=Integration"

test-backend-all: build-backend ## Run all backend tests including Integration (requires Docker)
	dotnet test AiTradingRace.Tests/AiTradingRace.Tests.csproj --configuration Release --no-build --verbosity normal

lint-backend: ## Check backend code formatting
	dotnet format AiTradingRace.Web/AiTradingRace.Web.csproj --verify-no-changes --verbosity normal

# ─── Frontend ───

build-frontend: ## Build frontend
	cd ai-trading-race-web && npm ci && npm run build

test-frontend: lint-frontend ## Run frontend checks (lint + type check + build, matching CI)
	cd ai-trading-race-web && npx tsc --noEmit
	cd ai-trading-race-web && npm run build

lint-frontend: ## Lint frontend
	cd ai-trading-race-web && npm ci --silent && npm run lint

# ─── ML Service ───

test-ml: lint-ml ## Run ML tests with coverage (matching CI)
	cd ai-trading-race-ml && pytest tests/ --cov=app --cov-report=term

lint-ml: ## Run ML linting (black + flake8 + mypy, matching CI)
	cd ai-trading-race-ml && black --check app/ tests/
	cd ai-trading-race-ml && flake8 app/ tests/ --max-line-length=100
	cd ai-trading-race-ml && mypy app/ --ignore-missing-imports
