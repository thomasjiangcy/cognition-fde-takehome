# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.11.28 AS uv


FROM python:3.14.6-alpine AS backend-builder

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project


FROM python:3.14.6-alpine AS runtime

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=backend-builder /app/.venv /app/.venv
COPY alembic.ini ./alembic.ini
COPY app ./app
COPY migrations ./migrations
COPY playbooks ./playbooks

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=2)"

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8080"]
