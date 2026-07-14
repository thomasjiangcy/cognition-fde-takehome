# GitHub to Devin webhook service

A small FastAPI service that will receive GitHub webhooks and start Devin
sessions. The webhook contract and Devin integration will be added as their
requirements are defined.

## Setup

Install the configured Python and `uv` versions, then install dependencies:

```shell
mise install
mise run install
```

The existing `.env` file is intentionally ignored by Git and is not needed by
the health-check scaffold.

## Run locally

```shell
mise run dev
```

The API is available at <http://127.0.0.1:8000>. Useful endpoints:

- `GET /health`
- `GET /docs`

## Test

```shell
mise run test
```
