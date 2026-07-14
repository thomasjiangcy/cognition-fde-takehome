# syntax=docker/dockerfile:1

FROM node:24-alpine AS frontend-builder

WORKDIR /build/frontend

RUN npm install --global pnpm@11.5.2

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN pnpm build


FROM ghcr.io/astral-sh/uv:0.9.30 AS uv


FROM python:3.12-alpine AS backend-builder

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project


FROM python:3.12-alpine AS runtime

RUN apk add --no-cache nginx tini

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=backend-builder /app/.venv /app/.venv
COPY api ./api
COPY docker/nginx.conf /etc/nginx/http.d/default.conf
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY --from=frontend-builder /build/frontend/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/api/health || exit 1

ENTRYPOINT ["/sbin/tini", "--", "/usr/local/bin/entrypoint.sh"]
