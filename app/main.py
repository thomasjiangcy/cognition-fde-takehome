from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import load_github_webhook_settings, load_observability_settings
from app.initialization import initialize_resources
from app.observability import Observability, configure_observability
from app.webhooks.github.router import create_github_webhook_router
from app.workflows.dispatcher import WorkflowDispatcher
from app.workflows.initial_workflow import BugInvestigationWorkflow

APP_DIR = Path(__file__).resolve().parent
scheduler = AsyncIOScheduler(timezone="UTC")
observability: Observability | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.resources = await initialize_resources()
    app.state.scheduler = scheduler
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        if observability is not None:
            observability.shutdown()


app = FastAPI(
    title="GitHub to Devin Automation Service",
    description="Runs webhook-driven, scheduled, and manual GitHub-to-Devin workflows.",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
observability = configure_observability(app, load_observability_settings())
dispatcher = WorkflowDispatcher([BugInvestigationWorkflow()])
app.include_router(
    create_github_webhook_router(load_github_webhook_settings(), dispatcher)
)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

templates = Jinja2Templates(directory=APP_DIR / "templates")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"scheduler_running": scheduler.running},
    )


@app.get("/api/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
