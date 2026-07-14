# GitHub to Devin automation service

A small FastAPI application for webhook-driven and manually triggered
GitHub-to-Devin workflows. FastAPI serves both the API and a basic
server-rendered dashboard.

At startup, the application runs a resource initialization hook. Registered
Devin playbooks are reconciled by unique macro: the initializer creates missing
playbooks, updates changed playbooks, and leaves matching playbooks untouched.

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

## Demo

The demo uses a repository webhook on a Superset fork. The webhook sends newly
opened issues through the public Cloudflare URL to the local FastAPI service.

### 1. Configure the environment

Copy `sample.env` to `.env`, then configure all values required by the demo:

```dotenv
DEVIN_ORG_ID=<Devin organization ID beginning with org->
DEVIN_API_KEY=<Devin API key beginning with cog_>
GITHUB_REPOSITORY=thomasjiangcy/superset
GITHUB_TOKEN=<fine-grained token with Issues write permission>
GITHUB_WEBHOOK_SECRET=<high-entropy webhook secret>
```

`DEVIN_ORG_ID` and `DEVIN_API_KEY` authorize access to the organization's Devin
resources. The service user needs `ManageAccountPlaybooks` for startup
reconciliation and `ManageOrgSessions` for workflow execution.
`GITHUB_REPOSITORY` is the fork that will receive the seeded issue.
`GITHUB_TOKEN` needs Issues write permission for that repository. Generate a
webhook secret if needed:

```shell
openssl rand -hex 32
```

Store that value as `GITHUB_WEBHOOK_SECRET`. The exact same value must be
entered in GitHub when registering the webhook. Configure `.env` before
starting the stack so Compose passes the secret into the application container.

### 2. Start the development stack

```shell
docker compose up --build -d
```

Confirm that the application is healthy:

```shell
curl --fail http://127.0.0.1:8080/api/health
```

Find the temporary public hostname:

```shell
docker compose logs tunnel
```

Look for an `https://<random-name>.trycloudflare.com` URL. The full webhook URL
is:

```text
https://<random-name>.trycloudflare.com/api/webhooks/github
```

### 3. Register the repository webhook

In the fork, open **Settings → Webhooks → Add webhook** and configure:

| GitHub field | Value |
|---|---|
| Payload URL | The full `/api/webhooks/github` URL above |
| Content type | **`application/json`** |
| Secret | The exact `GITHUB_WEBHOOK_SECRET` value from `.env` |
| SSL verification | Enable SSL verification |
| Events | Let me select individual events → **Issues** |
| Active | Enabled |

Do not select `application/x-www-form-urlencoded`; the receiver intentionally
accepts JSON webhook bodies only. When the webhook is created, GitHub sends a
`ping`. In **Recent Deliveries**, the ping should show response status `202`
with a response body similar to:

```json
{
  "delivery_id": "<delivery-guid>",
  "event": "ping",
  "action": null,
  "repository": "owner/repository",
  "status": "received"
}
```

If the first ping used the wrong settings, update the webhook and choose
**Redeliver** on that delivery. Common responses are:

| Status | Meaning |
|---:|---|
| `202` | Signature and payload were accepted |
| `403` | The signature is missing or the GitHub secret does not match `.env` |
| `415` | Content type is not `application/json` |
| `503` | `GITHUB_WEBHOOK_SECRET` was not configured when the app started |

Follow application and tunnel logs during the demo with:

```shell
docker compose logs --follow app tunnel
```

Cloudflare Quick Tunnel hostnames are temporary. If the tunnel is recreated,
update the webhook's Payload URL before testing again.

### 4. Route an unvalidated bug report

This scenario starts with
[apache/superset#39007](https://github.com/apache/superset/issues/39007), an
unvalidated Mixed Chart report that does not yet contain enough evidence for a
maintainer to begin implementation.

Optionally preview the exact issue without contacting GitHub:

```shell
mise exec -- uv run scripts/seed_issues.py mixed-chart-matrixify --dry-run
```

Create the issue in the configured fork and trigger the webhook:

```shell
mise exec -- uv run scripts/seed_issues.py mixed-chart-matrixify
```

The corresponding `issues` delivery should show response status `202`, action
`opened`, and status `received`. The application persists the verified delivery,
routes issues containing `### Bug description` to the bug-investigation
workflow, and starts a Devin session with the managed playbook and issue context.

The script creates the upstream `validation:required` label if necessary and
copies the upstream issue title and body exactly. It will not create another
copy while an exact match remains open. Close the previous demo issue before
rerunning the scenario to create a fresh issue and emit another `opened`
webhook.

Use `--repo OWNER/REPOSITORY` to override `GITHUB_REPOSITORY`, for example when
an assessor runs the scenario against their own fork.

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
