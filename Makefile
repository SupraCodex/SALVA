# Developer shortcuts. Requires Python 3.11+, Node 20+ and a PostgreSQL database
# (DATABASE_URL, default postgresql+psycopg://salva:salva@localhost:5432/salva).
.PHONY: install web migrate seed demo run test test-core test-ml test-backend test-web e2e lint docker

install:
	python -m pip install -e "core[dev,lgbm]" -e "backend[dev]" -r ml/requirements.txt -r e2e/requirements.txt
	cd frontend && npm install

web:
	cd frontend && npm run build

migrate:
	cd backend && alembic upgrade head

seed: migrate
	cd backend && python -m app.seed --reference

demo: migrate
	cd backend && python -m app.seed --reference --demo

run: web seed
	cd backend && uvicorn app.main:app --reload --port 8000

test: test-core test-ml test-backend test-web

test-core:
	python -m pytest core/tests -q

test-ml:
	python -m pytest ml/tests -q

test-backend:
	cd backend && python -m pytest -q

test-web:
	cd frontend && npm run typecheck && npm test

e2e:
	SALVA_URL=$${SALVA_URL:-http://127.0.0.1:8000} python -m pytest e2e -q

lint:
	ruff format --check core ml e2e && ruff check core ml e2e
	cd backend && ruff format --check . && ruff check . && mypy app

docker:
	docker compose up --build
