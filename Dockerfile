# One image: the built web interface served by the FastAPI application.
#   docker build -t salva .
#   docker compose up            (adds PostgreSQL, migrations and reference data)

FROM node:22-bookworm-slim AS web
WORKDIR /src/frontend
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run typecheck && npm run build

FROM python:3.11-slim-bookworm AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FRONTEND_DIST=/app/frontend/dist \
    REFERENCE_DIR=/app/data/reference \
    SALVA_REPO_ROOT=/app \
    FORWARDED_ALLOW_IPS=*
WORKDIR /app
# LightGBM (experimental model) needs the OpenMP runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

COPY core/ core/
COPY backend/pyproject.toml backend/
COPY backend/app backend/app
RUN pip install ./core "./backend[lgbm]"

COPY backend/alembic.ini backend/
COPY backend/migrations backend/migrations
COPY data/reference data/reference
COPY ml/artifacts/active.json ml/artifacts/active.json
COPY ml/artifacts/models ml/artifacts/models
COPY --from=web /src/frontend/dist frontend/dist

RUN useradd --system --uid 10001 salva && chown -R salva /app
USER salva
WORKDIR /app/backend
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed --reference $([ \"$SEED_DEMO\" = true ] && echo --demo) && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
