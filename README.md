# GitHub to Devin automation service

A small FastAPI application for scheduled and manually triggered
GitHub-to-Devin workflows. FastAPI serves both the API and a basic
server-rendered dashboard, while APScheduler provides an in-memory scheduling
primitive for the automation logic that will be added later.

At startup, the application runs a resource initialization hook before starting
the scheduler. The hook is currently a placeholder for future idempotent Devin
blueprint and playbook setup.

## Setup

Install the configured Python and `uv` versions, then install dependencies:

```shell
mise install
uv sync
```

The existing `.env` file is intentionally ignored by Git and is not needed by
the current scaffold.

## Run locally

```shell
uv run uvicorn app.main:app --reload
```

The application is available at <http://127.0.0.1:8000>. Useful endpoints:

- Dashboard: `GET /`
- Health check: `GET /api/health`
- API documentation: `GET /api/docs`

## Run with Docker

Build the image:

```shell
docker build -t github-devin-automation .
```

Run the application:

```shell
docker run -d \
  --name github-devin-automation \
  --env-file .env \
  -p 8080:8080 \
  github-devin-automation
```

The application is available at <http://127.0.0.1:8080>.

Stop and remove the container with:

```shell
docker rm -f github-devin-automation
```

## Test

```shell
uv run pytest
```
