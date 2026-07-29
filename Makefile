.PHONY: help up down logs build rebuild ps test test-core test-notify lint sync clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up:  ## Build and start the whole stack (detached)
	docker compose up --build -d

down:  ## Stop the stack
	docker compose down

clean:  ## Stop the stack and remove volumes (wipes the databases)
	docker compose down -v

logs:  ## Tail logs from all services
	docker compose logs -f

ps:  ## Show running services
	docker compose ps

build:  ## Build all images
	docker compose build

rebuild:  ## Rebuild images without cache
	docker compose build --no-cache

sync:  ## Install/refresh the Python workspace venv
	uv sync --all-packages

test: test-core test-notify  ## Run all backend test suites

test-core:  ## Run core-api tests
	uv run pytest services/core-api/tests -q

test-notify:  ## Run notification-service tests
	uv run --project . pytest services/notification-service/tests -q

lint:  ## Lint the Python code
	uv run ruff check services packages
