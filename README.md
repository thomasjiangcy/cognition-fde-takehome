# GitHub to Devin webhook service

A FastAPI service that will receive GitHub webhooks and start Devin sessions,
with a React and Vite frontend for reporting. The webhook contract and Devin
integration will be added as their requirements are defined.

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
docker build -t github-devin-webhooks .
```

Run the frontend and API together:

```shell
docker run -d \
  --name github-devin-webhooks \
  --env-file .env \
  -p 8080:8080 \
  github-devin-webhooks
```

The application is available at <http://127.0.0.1:8080>, with the API exposed
under `/api`. Useful container endpoints:

- `GET /api/health`
- `GET /api/docs`

Stop and remove the container with:

```shell
docker rm -f github-devin-webhooks
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

Look for an `https://<random-name>.trycloudflare.com` URL. The dashboard and
API are available through that hostname; the future GitHub webhook endpoint
will use a URL such as
`https://<random-name>.trycloudflare.com/api/webhooks/github`.

Quick Tunnel hostnames are temporary and normally change when the tunnel is
recreated. A named Cloudflare Tunnel can be added later if the webhook needs a
stable hostname.

Stop both services with:

```shell
docker compose down
```

## Test

```shell
uv run pytest
pnpm --dir frontend build
```
