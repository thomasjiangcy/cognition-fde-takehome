# GitHub to Devin automation service

A small FastAPI application for webhook-driven and manually triggered
GitHub-to-Devin workflows. FastAPI serves both the API and a basic
server-rendered dashboard.

At startup, the application runs a resource initialization hook. Registered
Devin playbooks are reconciled by unique macro: the initializer creates missing
playbooks and upserts existing ones to the local definition.

## Setup

Install the configured tools and Python dependencies, then enable the Git hooks:

```shell
mise install
mise exec -- uv sync
mise exec -- lefthook install
```

Copy `sample.env` to `.env` and fill in the values needed for the workflow:

```shell
cp sample.env .env
```

The `.env` file is intentionally ignored by both Git and the Docker build
context. `GITHUB_WEBHOOK_SECRET` should contain the same high-entropy secret
configured on the repository webhook.

## Demo

The demo creates reproducible Superset bug-report issues in a fork and routes
them through the same bug-investigation workflow that a real GitHub webhook
would trigger.

> **Why a button instead of a webhook?** Reviewers typically do not have admin
> access to the fork repository, which means they cannot register a webhook URL
> under **Settings → Webhooks**. The dashboard's **Simulate issue workflow**
> button works around this by creating the issue directly through the GitHub
> REST API and then dispatching the same `issues.opened` payload through the
> workflow dispatcher — no webhook registration required. In production, a
> registered webhook would deliver the same payload automatically.

### 1. Configure the environment

Copy `sample.env` to `.env`, then configure the values required by the demo:

```dotenv
DEVIN_ORG_ID=<Devin organization ID beginning with org->
DEVIN_API_KEY=<Devin API key beginning with cog_>
GITHUB_TOKEN=<fine-grained token with Issues read/write and Metadata read>
```

`DEVIN_ORG_ID` and `DEVIN_API_KEY` authorize access to the organization's Devin
resources. The service user needs `ManageAccountPlaybooks` for startup
reconciliation and `ManageOrgSessions` for workflow execution.
`GITHUB_TOKEN` must be a fine-grained token (or classic PAT with `public_repo`
scope) with Issues read/write permission on the fork; it is used to create
labels, create issues, and add labels to issues.

The remaining `sample.env` values are handled by Compose defaults and do not
need to be set: `DATABASE_URL`, `POSTGRES_DB`, `POSTGRES_USER`, and
`POSTGRES_PASSWORD` default to the Compose PostgreSQL service, and
`GITHUB_WEBHOOK_SECRET` is optional (the simulate flow does not use webhooks).
Configure `.env` before starting the stack so Compose passes the values into
the application container.

### 2. Start the development stack

```shell
docker compose up --build -d
```

Confirm that the application is healthy:

```shell
curl --fail http://127.0.0.1:8080/api/health
```

Open the dashboard at <http://127.0.0.1:8080>.

Follow application logs during the demo with:

```shell
docker compose logs --follow app
```

### 3. Simulate issue workflow

Click **Simulate issue workflow** on the dashboard, or run the equivalent
curl command:

```shell
curl -X POST http://127.0.0.1:8080/api/jobs/simulate-issue
```

The application creates all configured demo issues in the fork (creating any
missing labels first), then dispatches each issue through the same
`issues.opened` workflow that a real webhook would trigger. The dashboard
polls every 5 seconds and shows each workflow run's status, Devin session
link, and completion state.

Each click or curl creates fresh issues, so the demo can be repeated without
closing previous issues. The bug-investigation workflow starts a Devin session
with the managed playbook and issue context for each issue containing
`### Bug description`.

Once an issue has been investigated and labeled `validation:validated`, click
**Run bug-fix job** to launch a Devin session that fixes the bug and opens a
pull request.

## Structure

- `app/webhooks/github` owns GitHub webhook transport, verification, and
  normalized deliveries.
- `app/workflows` selects and runs zero or more workflows for each delivery.
- `app/automation` owns generic trigger event and workflow run persistence.
- `app/devin` owns Devin API clients and managed resources.
- `playbooks` contains Markdown bodies for application-managed Devin playbooks.
- `app/initialization.py` is the startup boundary for idempotent Devin resource
  setup.

## Run

Docker Compose is the single interface for running the application. Development
and production run the same application, PostgreSQL, LGTM observability, and
Cloudflare tunnel services; only the application container's source and command
differ.

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
- PostgreSQL on `127.0.0.1:5432`
- Grafana: <http://127.0.0.1:3000> using `admin` / `admin`
- A temporary Cloudflare Quick Tunnel

The application runs `alembic upgrade head` before Uvicorn starts. Compose uses
`automation` for the local database, user, and password. Override
`DATABASE_URL`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` together
when using different credentials.

Find the generated public URL in the tunnel logs:

```shell
docker compose logs tunnel
```

Look for an `https://<random-name>.trycloudflare.com` URL. The GitHub webhook
URL is:

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
non-reloading Uvicorn command. It starts the same PostgreSQL, LGTM, and
Cloudflare tunnel services as development mode, without source mounts or hot
reload.

Stop production mode with:

```shell
docker compose -f compose.yaml down
```

## Test

The default pytest suite is hermetic and includes AnyIO support for asynchronous
application tests:

```shell
mise exec -- uv run pytest
```

PostgreSQL integration tests use Testcontainers to start and remove isolated
PostgreSQL 18.4 containers. Docker must be available; no Compose service needs
to be started manually:

```shell
mise exec -- uv run pytest -m database tests/integration
```

Opt-in live integration tests use the configured `.env` credentials and create
isolated resources in Devin. Each test removes the playbooks it creates:

```shell
mise exec -- uv run pytest -m live tests/integration
```

## Code quality

Format Python code with Ruff:

```shell
mise exec -- uv run ruff format .
```

Run formatting, linting, and type-checking verification:

```shell
mise exec -- uv run ruff format --check .
mise exec -- uv run ruff check .
mise exec -- uv run ty check
```

## Git hooks

Lefthook validates each commit message with Commitizen's Conventional Commits
rules. It also runs Ruff's safe fixes and formatter on staged Python files before
each commit, then stages the resulting files. Before each push, it runs the Ruff
checks, type checker, and test suite in parallel.

Lefthook preserves unstaged changes while applying `stage_fixed`, so partially
staged files remain partially staged after formatting. Run the hooks manually
across the repository with:

```shell
mise exec -- lefthook run pre-commit --all-files --no-stage-fixed
mise exec -- lefthook run pre-push --force
```
