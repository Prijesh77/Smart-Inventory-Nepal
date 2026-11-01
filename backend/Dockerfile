# API image. Build context is the PROJECT ROOT (the API reuses ../ml):
#   docker compose build api
FROM python:3.12.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements-api.txt backend/requirements-api.txt
RUN pip install -r backend/requirements-api.txt

# Code only. Data, trained models and experiment results are mounted at run time
# (see docker-compose.yml): M5 data may not be redistributed inside an image.
COPY ml/ ml/
COPY backend/ backend/

# Run as a normal user, not root.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

WORKDIR /app/backend
EXPOSE 8000

# Apply database migrations, then start the API.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
