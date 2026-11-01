# API image. Build context is the PROJECT ROOT (the API reuses ../ml):
#   docker compose build api
FROM python:3.12.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements-api.txt backend/requirements-api.txt
RUN pip install -r backend/requirements-api.txt

# Code only. Each shop's trained models are written to /app/models, a Docker volume
# (see docker-compose.yml), so they survive rebuilds.
COPY ml/ ml/
COPY backend/ backend/

# Run as a normal user, not root. The models folder is created here, owned by that user,
# so the new volume gets the same owner and the API can save trained models.
RUN useradd --create-home --uid 10001 appuser && mkdir -p /app/models && chown -R appuser /app
USER appuser

WORKDIR /app/backend
EXPOSE 8000

# Apply database migrations, then start the API.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
