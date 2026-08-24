.PHONY: bootstrap dev migrate seed test test-contracts lint typecheck build

bootstrap:
	uv sync --all-extras --dev
	npm install

dev:
	docker compose -f infra/compose/compose.yaml up --build postgres redis api worker agent-worker web

migrate:
	uv run alembic -c infra/migrations/alembic.ini upgrade head

seed:
	uv run python -m modules.agents.registry

test:
	uv run pytest
	npm test

test-contracts:
	uv run pytest tests/contract
	npm run test:contracts

lint:
	uv run ruff check .
	npm run lint

typecheck:
	uv run mypy
	npm exec tsc --workspace apps/web -- --noEmit

build:
	npm run build

