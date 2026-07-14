# GitHub to Devin automation service

A FastAPI service for scheduled and manually triggered GitHub-to-Devin
workflows, with a React and Vite frontend for reporting. The automation logic
will be added as its requirements are defined.

## Setup

Install the configured tools, then install the backend and frontend dependencies:

```shell
mise install
uv sync
pnpm --dir frontend install
```

The existing `.env` file is intentionally ignored by Git and is not needed by
the health-check scaffold.

## Run locally

Start the API:

```shell
uv run uvicorn api.main:app --reload
```

The API is available at <http://127.0.0.1:8000>. Useful endpoints:

- `GET /health`
- `GET /docs`

In a second terminal, start the frontend:

```shell
pnpm --dir frontend dev
```

The dashboard is available at <http://127.0.0.1:5173>.

## Run with Docker

Build the single-container image:

```shell
docker build -t github-devin-automation .
```

Run the frontend and API together:

```shell
docker run -d \
  --name github-devin-automation \
  --env-file .env \
  -p 8080:8080 \
  github-devin-automation
```

The application is available at <http://127.0.0.1:8080>, with the API exposed
under `/api`. Useful container endpoints:

- `GET /api/health`
- `GET /api/docs`

Stop and remove the container with:

```shell
docker rm -f github-devin-automation
```

## Test

```shell
uv run pytest
pnpm --dir frontend build
```
