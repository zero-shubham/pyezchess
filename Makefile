.PHONY: dev up down build clean lint format typecheck test req req-prod migrate-up migrate-down

dev: req
	docker compose up --build

up:
	docker compose up -d

down:
	docker compose down

build:
	docker build -t pyezchess -f Dockerfile-build .

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

lint:
	ruff check .

format:
	ruff format .

typecheck:
	pyright

test:
	pytest -v

req:
	uv export --format requirements-txt --extra dev --no-emit-package pyezchess > requirements.txt

req-prod:
	uv export --format requirements-txt --no-dev --no-emit-package pyezchess > requirements.txt

migrate-up:
	docker compose run --rm app python -m cli.main migrate up

migrate-down:
	docker compose run --rm app python -m cli.main migrate down
