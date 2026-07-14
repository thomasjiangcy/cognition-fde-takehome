# GitHub to Devin automation service

A small FastAPI application for webhook-driven, scheduled, and manually
triggered GitHub-to-Devin workflows. FastAPI serves both the API and a basic
server-rendered dashboard, while APScheduler provides an in-memory scheduling
primitive for the automation logic that will be added later.

At startup, the application runs a resource initialization hook before starting
the scheduler. Registered Devin playbooks are reconciled by unique macro: the
initializer creates missing playbooks, updates changed playbooks, and leaves
matching playbooks untouched. No playbooks are registered yet, so the current
scaffold does not contact Devin during startup.

## Setup

Install the configured tools and Python dependencies, then enable the Git hooks:

```shell
mise install
uv sync
lefthook install
```

Copy `sample.env` to `.env` and fill in the values needed for the workflow:

```shell
cp sample.env .env
```

The `.env` file is intentionally ignored by both Git and the Docker build
context. `GITHUB_WEBHOOK_SECRET` should contain the same high-entropy secret
configured on the repository webhook.

## Structure

- `app/github/webhooks` owns GitHub webhook transport, verification, and
  normalized deliveries.
- `app/workflows` selects and runs zero or more workflows for each delivery.
- `app/devin` is the first-class home for Devin clients, resources, and
  sessions.
- `playbooks` contains Markdown bodies for application-managed Devin playbooks.
- `app/initialization.py` is the startup boundary for idempotent Devin resource
  setup.

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

## Run with a public development URL

Docker Compose starts the application and a Cloudflare Quick Tunnel together:

```shell
docker compose up -d --build
```

Find the generated public URL in the tunnel logs:

```shell
docker compose logs tunnel
```

Look for an `https://<random-name>.trycloudflare.com` URL. The planned GitHub
webhook URL will be:

```text
https://<random-name>.trycloudflare.com/api/webhooks/github
```

Quick Tunnel hostnames are temporary and intended for development and demos.
They normally change when the tunnel is recreated.

Stop both services with:

```shell
docker compose down
```

## Test

The project uses pytest, including AnyIO support for async application tests:

```shell
uv run pytest
```

## Code quality

Format Python code with Ruff:

```shell
uv run ruff format .
```

Run formatting, linting, and type-checking verification:

```shell
uv run ruff format --check .
uv run ruff check .
uv run ty check
```

## Git hooks

Lefthook runs Ruff's safe fixes and formatter on staged Python files before
each commit, then stages the resulting files. Before each push, it runs the
Ruff checks, type checker, and test suite in parallel.

Lefthook preserves unstaged changes while applying `stage_fixed`, so partially
staged files remain partially staged after formatting. Run the hooks manually
across the repository with:

```shell
lefthook run pre-commit --all-files --no-stage-fixed
lefthook run pre-push --force
```
