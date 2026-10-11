# API SALVA. Build context: this backend/ folder.
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/backend

COPY pyproject.toml ./
COPY app ./app
RUN pip install . && useradd --create-home salva

COPY alembic.ini ./
COPY migrations ./migrations
RUN chown -R salva /srv
USER salva

EXPOSE 8000
# Create/upgrade the PostgreSQL schema, then start the API
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
