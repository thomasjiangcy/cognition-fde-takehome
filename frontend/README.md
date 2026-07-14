# Devin automation dashboard

React and Vite frontend for scheduled and manual GitHub-to-Devin automation.

From the repository root:

```shell
pnpm --dir frontend install
pnpm --dir frontend dev
```

The Vite development server proxies `/api/*` requests to the FastAPI service at
`http://127.0.0.1:8000`.
