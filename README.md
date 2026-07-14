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

## Run

Docker Compose is the single interface for running the application. Development
and production run the same application, LGTM observability, and Cloudflare
tunnel services; only the application container's source and command differ.

### Development

Start the complete development stack:

```shell
docker compose up --build
```

Compose automatically applies `compose.override.yaml`, which bind-mounts
`app/` and `playbooks/` into the container and replaces the production command
with Uvicorn's reload mode. Python source changes restart the server without an
image rebuild.

The development stack includes:

- Application: <http://127.0.0.1:8080>
- API documentation: <http://127.0.0.1:8080/api/docs>
- Health check: <http://127.0.0.1:8080/api/health>
- Grafana: <http://127.0.0.1:3000> using `admin` / `admin`
- A temporary Cloudflare Quick Tunnel

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

Stop the development stack with `Ctrl+C`, or from another terminal:

```shell
docker compose down
```

### Production

Run only the production definition, without the development override:

```shell
docker compose -f compose.yaml up -d --build
```

Production mode uses the source baked into the image and the Dockerfile's
non-reloading Uvicorn command. It starts the same LGTM and Cloudflare tunnel
services as development mode, without source mounts or hot reload.

Stop production mode with:

```shell
docker compose -f compose.yaml down
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
