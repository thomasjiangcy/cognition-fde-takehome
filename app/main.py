from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.automation.dashboard import DashboardService, DashboardSnapshot
from app.config import (
    DatabaseSettings,
    DevinSettings,
    GitHubTokenSettings,
    load_database_settings,
    load_devin_settings,
    load_github_webhook_settings,
    load_observability_settings,
)
from app.database import Database
from app.devin.client import DevinClient
from app.devin.sessions import DevinSessions
from app.github.client import GitHubClient
from app.initialization import initialize_resources
from app.observability import Observability, configure_observability
from app.webhooks.github.router import create_github_webhook_router
from app.workflows.bug_fix import BUG_FIX_PLAYBOOK, BugFixWorkflow
from app.workflows.bug_investigation import (
    BUG_INVESTIGATION_PLAYBOOK,
    BugInvestigationWorkflow,
)
from app.workflows.dispatcher import WorkflowDispatcher

APP_DIR = Path(__file__).resolve().parent
dashboard_service = DashboardService()
observability: Observability | None = None


@asynccontextmanager
async def lifespan(
    app: FastAPI,
    *,
    database_settings: DatabaseSettings | None = None,
    devin_settings: DevinSettings | None = None,
    devin_transport: httpx.AsyncBaseTransport | None = None,
) -> AsyncIterator[None]:
    resolved_devin_settings = (
        devin_settings if devin_settings is not None else load_devin_settings()
    )
    resources = await initialize_resources(
        settings=resolved_devin_settings,
        transport=devin_transport,
    )
    app.state.resources = resources
    database = Database.create(
        database_settings if database_settings is not None else load_database_settings()
    )
    github_token_settings = GitHubTokenSettings()
    try:
        async with AsyncExitStack() as stack:
            client = await stack.enter_async_context(
                DevinClient(
                    api_key=resolved_devin_settings.devin_api_key,
                    transport=devin_transport,
                )
            )
            sessions = DevinSessions(client, resolved_devin_settings.devin_org_id)
            github_client: GitHubClient | None = None
            if github_token_settings.github_token is not None:
                github_client = await stack.enter_async_context(
                    GitHubClient(github_token_settings.github_token)
                )
            workflows: list[BugInvestigationWorkflow | BugFixWorkflow] = [
                BugInvestigationWorkflow(
                    sessions,
                    resources.playbook_ids[BUG_INVESTIGATION_PLAYBOOK.macro],
                )
            ]
            if github_client is not None:
                workflows.append(
                    BugFixWorkflow(
                        sessions,
                        github_client,
                        resources.playbook_ids[BUG_FIX_PLAYBOOK.macro],
                    )
                )
            dispatcher.configure(database, workflows)
            dashboard_service.configure(
                database,
                sessions,
                github_client,
                dispatcher,
            )
            yield
    finally:
        await database.close()
        if observability is not None:
            observability.shutdown()


app = FastAPI(
    title="GitHub to Devin Automation Service",
    description="Runs webhook-driven and manual GitHub-to-Devin workflows.",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
observability = configure_observability(app, load_observability_settings())
dispatcher = WorkflowDispatcher()
app.include_router(
    create_github_webhook_router(load_github_webhook_settings(), dispatcher)
)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

templates = Jinja2Templates(directory=APP_DIR / "templates")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/dashboard", tags=["dashboard"])
async def dashboard_data() -> DashboardSnapshot:
    return await dashboard_service.snapshot()


@app.get("/api/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/jobs/bug-fix", tags=["jobs"])
async def run_bug_fix(repository: str = "thomasjiangcy/superset") -> dict[str, int]:
    results = await dashboard_service.run_bug_fix(repository)
    return {"started": len(results)}


@app.post("/api/jobs/simulate-issue", tags=["jobs"])
async def simulate_issue_workflow(
    repository: str = "thomasjiangcy/superset",
) -> dict[str, int]:
    results = await dashboard_service.simulate_issue_workflow(repository)
    return {"started": len(results)}
