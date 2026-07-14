import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

import httpx
from pydantic import AnyHttpUrl, AwareDatetime, BaseModel, ConfigDict, ValidationError
from sqlalchemy import func, select

from app.automation.models import TriggerEvent, WorkflowRun, WorkflowRunState
from app.automation.repository import AutomationRepository, TriggerEventData
from app.database import Database
from app.devin.models import DevinSession, DevinSessionStatus, DevinSessionStatusDetail
from app.devin.sessions import DevinSessions
from app.github.client import GitHubClient
from app.webhooks.github.models import (
    GitHubDelivery,
    GitHubIssuesPayload,
    GitHubRepository,
    GitHubUser,
)
from app.workflows.dispatcher import WorkflowDispatcher, WorkflowResult

logger = logging.getLogger(__name__)
MAX_CONCURRENT_SESSION_REFRESHES = 8


class DashboardMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    completed: int
    in_progress: int
    failed: int


class DashboardRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: UUID
    state: WorkflowRunState
    source: str
    event_type: str
    subject_title: str | None
    subject_url: AnyHttpUrl | None
    workflow_name: str
    devin_session_id: str | None
    devin_session_url: AnyHttpUrl | None
    created_at: AwareDatetime


class DashboardSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    metrics: DashboardMetrics
    runs: list[DashboardRun]
    generated_at: AwareDatetime


class DashboardService:
    def __init__(self) -> None:
        self._database: Database | None = None
        self._sessions: DevinSessions | None = None
        self._github_client: GitHubClient | None = None
        self._dispatcher: WorkflowDispatcher | None = None

    def configure(
        self,
        database: Database,
        sessions: DevinSessions,
        github_client: GitHubClient | None = None,
        dispatcher: WorkflowDispatcher | None = None,
    ) -> None:
        self._database = database
        self._sessions = sessions
        self._github_client = github_client
        self._dispatcher = dispatcher

    async def run_bug_fix(self, repository: str) -> list[WorkflowResult]:
        """Scan validated issues and launch a fix session for each unassigned one."""
        github_client = self._require_github_client()
        dispatcher = self._require_dispatcher()
        issues = await github_client.list_issues(
            repository,
            labels=("validation:validated",),
            state="open",
        )
        results: list[WorkflowResult] = []
        for issue in issues:
            if any(label.name == "devin:assigned" for label in issue.labels):
                continue
            delivery = GitHubDelivery(
                delivery_id=f"manual-{issue.number}",
                event="manual",
                action=None,
                repository=repository,
                payload=GitHubIssuesPayload(
                    action="manual",
                    issue=issue,
                    repository=GitHubRepository(full_name=repository),
                    sender=GitHubUser(login="github-devin-automation"),
                ),
            )
            event = TriggerEventData(
                source="dashboard",
                external_id=f"{repository}:{issue.number}",
                event_type="manual",
                action=None,
                subject_type="issue",
                subject_id=str(issue.number),
                subject_title=issue.title,
                subject_url=AnyHttpUrl(issue.html_url),
                received_at=datetime.now(UTC),
            )
            prepared = await dispatcher.prepare(delivery, event)
            for prepared_workflow in prepared:
                workflow_results = await dispatcher.execute(
                    (prepared_workflow,),
                    delivery,
                )
                results.extend(workflow_results)
        return results

    async def snapshot(self) -> DashboardSnapshot:
        database = self._require_database()
        await self._refresh_active_sessions(database, self._require_sessions())
        async with database.sessions() as session:
            state_count_rows = (
                await session.execute(
                    select(WorkflowRun.state, func.count(WorkflowRun.id)).group_by(
                        WorkflowRun.state
                    )
                )
            ).tuples()
            state_counts = {state: count for state, count in state_count_rows}
            records = await session.execute(
                select(WorkflowRun, TriggerEvent)
                .join(
                    TriggerEvent,
                    TriggerEvent.id == WorkflowRun.trigger_event_id,
                )
                .order_by(WorkflowRun.created_at.desc())
                .limit(100)
            )

        runs = [self._run_model(run, event) for run, event in records]
        return DashboardSnapshot(
            metrics=DashboardMetrics(
                completed=state_counts.get(WorkflowRunState.COMPLETED, 0),
                in_progress=(
                    state_counts.get(WorkflowRunState.QUEUED, 0)
                    + state_counts.get(WorkflowRunState.IN_PROGRESS, 0)
                ),
                failed=state_counts.get(WorkflowRunState.FAILED, 0),
            ),
            runs=runs,
            generated_at=datetime.now(UTC),
        )

    @staticmethod
    async def _refresh_active_sessions(
        database: Database,
        sessions: DevinSessions,
    ) -> None:
        async with database.sessions() as database_session:
            active_runs = tuple(
                await database_session.execute(
                    select(WorkflowRun.id, WorkflowRun.devin_session_id).where(
                        WorkflowRun.state == WorkflowRunState.IN_PROGRESS,
                        WorkflowRun.devin_session_id.is_not(None),
                    )
                )
            )

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_SESSION_REFRESHES)
        refreshes = await asyncio.gather(
            *(
                DashboardService._fetch_session(
                    run_id,
                    session_id,
                    sessions,
                    semaphore,
                )
                for run_id, session_id in active_runs
                if session_id is not None
            )
        )
        successful_refreshes = tuple(
            refresh for refresh in refreshes if refresh is not None
        )
        if not successful_refreshes:
            return

        sessions_to_terminate: list[str] = []
        async with database.sessions.begin() as database_session:
            repository = AutomationRepository(database_session)
            for run_id, devin_session in successful_refreshes:
                state = DashboardService._state_for_session(devin_session)
                await repository.update_devin_status(
                    run_id,
                    state=state,
                    status=devin_session.status.value,
                    status_detail=(
                        devin_session.status_detail.value
                        if devin_session.status_detail is not None
                        else None
                    ),
                )
                if (
                    state == WorkflowRunState.COMPLETED
                    and DashboardService._should_terminate(devin_session)
                ):
                    sessions_to_terminate.append(devin_session.session_id)

        for session_id in sessions_to_terminate:
            try:
                await sessions.terminate(session_id)
            except httpx.HTTPError:
                logger.warning(
                    "Unable to terminate completed Devin session",
                    extra={"devin_session_id": session_id},
                    exc_info=True,
                )

    @staticmethod
    async def _fetch_session(
        run_id: UUID,
        session_id: str,
        sessions: DevinSessions,
        semaphore: asyncio.Semaphore,
    ) -> tuple[UUID, DevinSession] | None:
        try:
            async with semaphore:
                return run_id, await sessions.get(session_id)
        except httpx.HTTPError, ValidationError:
            logger.warning(
                "Unable to refresh Devin session",
                extra={"devin_session_id": session_id},
                exc_info=True,
            )
            return None

    @staticmethod
    def _state_for_session(session: DevinSession) -> WorkflowRunState:
        if (
            session.status is DevinSessionStatus.EXIT
            or session.status_detail is DevinSessionStatusDetail.FINISHED
        ):
            return WorkflowRunState.COMPLETED
        if DashboardService._has_final_output(session):
            return WorkflowRunState.COMPLETED
        if session.status in {
            DevinSessionStatus.ERROR,
            DevinSessionStatus.SUSPENDED,
        }:
            return WorkflowRunState.FAILED
        return WorkflowRunState.IN_PROGRESS

    @staticmethod
    def _has_final_output(session: DevinSession) -> bool:
        return (
            session.status is DevinSessionStatus.RUNNING
            and session.status_detail is DevinSessionStatusDetail.WAITING_FOR_USER
            and session.structured_output is not None
        )

    @staticmethod
    def _should_terminate(session: DevinSession) -> bool:
        """Only terminate sessions that are complete but still Devin-side idle.

        ``exit`` or ``finished`` sessions are already terminal; a
        ``waiting_for_user`` session with a populated structured output is the
        one we need to clean up so it does not appear "awaiting instructions".
        """
        return (
            session.status is DevinSessionStatus.RUNNING
            and session.status_detail is DevinSessionStatusDetail.WAITING_FOR_USER
            and session.structured_output is not None
        )

    @staticmethod
    def _run_model(run: WorkflowRun, event: TriggerEvent) -> DashboardRun:
        session_url = (
            AnyHttpUrl(f"https://app.devin.ai/sessions/{run.devin_session_id}")
            if run.devin_session_id is not None
            else None
        )
        return DashboardRun(
            id=run.id,
            state=run.state,
            source=event.source,
            event_type=event.event_type,
            subject_title=event.subject_title,
            subject_url=(
                AnyHttpUrl(event.subject_url) if event.subject_url is not None else None
            ),
            workflow_name=run.workflow_name,
            devin_session_id=run.devin_session_id,
            devin_session_url=session_url,
            created_at=run.created_at,
        )

    def _require_database(self) -> Database:
        if self._database is None:
            raise RuntimeError("Dashboard service is not configured")
        return self._database

    def _require_sessions(self) -> DevinSessions:
        if self._sessions is None:
            raise RuntimeError("Dashboard service is not configured")
        return self._sessions

    def _require_github_client(self) -> GitHubClient:
        if self._github_client is None:
            raise RuntimeError("GitHub client is not configured")
        return self._github_client

    def _require_dispatcher(self) -> WorkflowDispatcher:
        if self._dispatcher is None:
            raise RuntimeError("Workflow dispatcher is not configured")
        return self._dispatcher
