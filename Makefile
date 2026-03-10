.PHONY: up down build logs ps test lint format clean

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build --no-cache

logs:
	docker compose logs -f

ps:
	docker compose ps

restart:
	docker compose down && docker compose up -d

shell-gateway:
	docker compose exec api-gateway bash

shell-db:
	docker compose exec postgres psql -U appuser -d aiplatform

test:
	pytest tests/ -v --asyncio-mode=auto

test-cov:
	pytest tests/ -v --asyncio-mode=auto --cov=. --cov-report=html

lint:
	ruff check .
	mypy . --ignore-missing-imports

format:
	ruff format .

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete
	docker compose down -v --remove-orphans
