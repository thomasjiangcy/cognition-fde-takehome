import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from pydantic import AnyHttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.dashboard import DashboardService
from app.automation.models import WorkflowRunState
from app.automation.repository import AutomationRepository, TriggerEventData
from app.database import Database
from app.devin.client import DevinClient
from app.devin.sessions import DevinSessions

pytestmark = [pytest.mark.anyio, pytest.mark.database]


@pytest.fixture
async def database_session(
    database: Database,
) -> AsyncIterator[AsyncSession]:
    async with database.sessions() as session:
        try:
            yield session
        finally:
            await session.rollback()


def _event(
    *, source: str = "github", external_id: str | None = None
) -> TriggerEventData:
    return TriggerEventData(
        source=source,
        external_id=external_id if external_id is not None else uuid4().hex,
        event_type="issues",
        action="opened",
        subject_type="issue",
        subject_id="octocat/superset#1347",
        subject_title="Mixed Chart matrixify does not apply to Query B",
        subject_url=AnyHttpUrl("https://github.com/octocat/superset/issues/1347"),
        received_at=datetime.now(UTC),
    )


async def test_registers_generic_event_with_selected_workflows(
    database_session: AsyncSession,
) -> None:
    repository = AutomationRepository(database_session)

    runs = await repository.register_event(
        _event(),
        ("bug-investigation", "maintainer-notification"),
    )

    assert [run.workflow_name for run in runs] == [
        "bug-investigation",
        "maintainer-notification",
    ]
    assert all(run.state is WorkflowRunState.QUEUED for run in runs)
    assert len({run.trigger_event_id for run in runs}) == 1


async def test_redelivery_reuses_event_and_workflow_run(
    database_session: AsyncSession,
) -> None:
    repository = AutomationRepository(database_session)
    event = _event()

    first = await repository.register_event(event, ("bug-investigation",))
    second = await repository.register_event(event, ("bug-investigation",))

    assert len(first) == 1
    assert len(second) == 1
    assert second[0].id == first[0].id
    assert second[0].trigger_event_id == first[0].trigger_event_id


async def test_dashboard_projects_metrics_and_session_links(
    database: Database,
) -> None:
    async with database.sessions.begin() as session:
        repository = AutomationRepository(session)
        runs = await repository.register_event(
            _event(),
            ("bug-investigation",),
        )
        claimed = await repository.claim_run(runs[0].id)
        await repository.record_devin_session(
            runs[0].id,
            session_id="devin-dashboard",
            status="running",
            status_detail="working",
        )

    def handle_devin_request(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "session_id": "devin-dashboard",
                "url": "https://app.devin.ai/sessions/devin-dashboard",
                "status": "exit",
                "status_detail": "finished",
                "tags": ["github-automation", "bug-investigation"],
                "org_id": "org-test",
                "created_at": 1,
                "updated_at": 2,
                "acus_consumed": 1.0,
                "pull_requests": [],
            },
        )

    transport = httpx.MockTransport(handle_devin_request)
    async with DevinClient(
        "cog_test",
        base_url="https://api.devin.test/v3/",
        transport=transport,
    ) as client:
        dashboard = DashboardService()
        dashboard.configure(database, DevinSessions(client, "org-test"))
        snapshot = await dashboard.snapshot()

    assert claimed is True
    assert snapshot.metrics.completed == 1
    assert snapshot.metrics.in_progress == 0
    assert snapshot.metrics.failed == 0
    assert len(snapshot.runs) == 1
    assert str(snapshot.runs[0].devin_session_url) == (
        "https://app.devin.ai/sessions/devin-dashboard"
    )


async def test_dashboard_detects_completion_from_structured_output_and_terminates(
    database: Database,
) -> None:
    async with database.sessions.begin() as session:
        repository = AutomationRepository(session)
        runs = await repository.register_event(
            _event(),
            ("bug-investigation",),
        )
        assert await repository.claim_run(runs[0].id) is True
        await repository.record_devin_session(
            runs[0].id,
            session_id="devin-waiting",
            status="running",
            status_detail="working",
        )

    received_requests: list[httpx.Request] = []

    def handle_devin_request(request: httpx.Request) -> httpx.Response:
        received_requests.append(request)
        session_id = request.url.path.rsplit("/", maxsplit=1)[-1]

        if request.method == "DELETE":
            assert session_id == "devin-waiting"
            return httpx.Response(
                200,
                json={
                    "session_id": "devin-waiting",
                    "url": "https://app.devin.ai/sessions/devin-waiting",
                    "status": "running",
                    "status_detail": None,
                    "tags": ["github-automation", "bug-investigation"],
                    "org_id": "org-test",
                    "created_at": 1,
                    "updated_at": 2,
                    "acus_consumed": 1.0,
                    "pull_requests": [],
                },
            )

        return httpx.Response(
            200,
            json={
                "session_id": "devin-waiting",
                "url": "https://app.devin.ai/sessions/devin-waiting",
                "status": "running",
                "status_detail": "waiting_for_user",
                "structured_output": {
                    "outcome": "confirmed",
                    "summary": "Matrixify does not apply to Query B.",
                    "issue_comment_url": "https://github.com/octocat/superset/issues/1347#issuecomment-1",
                    "root_cause": "adhoc_filters_b is not updated.",
                },
                "tags": ["github-automation", "bug-investigation"],
                "org_id": "org-test",
                "created_at": 1,
                "updated_at": 2,
                "acus_consumed": 1.0,
                "pull_requests": [],
            },
        )

    transport = httpx.MockTransport(handle_devin_request)
    async with DevinClient(
        "cog_test",
        base_url="https://api.devin.test/v3/",
        transport=transport,
    ) as client:
        dashboard = DashboardService()
        dashboard.configure(database, DevinSessions(client, "org-test"))
        snapshot = await dashboard.snapshot()

    assert snapshot.metrics.completed == 1
    assert snapshot.metrics.in_progress == 0
    assert snapshot.metrics.failed == 0
    assert len(snapshot.runs) == 1
    assert snapshot.runs[0].state == WorkflowRunState.COMPLETED
    assert any(
        request.method == "DELETE"
        and request.url.path == "/v3/organizations/org-test/sessions/devin-waiting"
        for request in received_requests
    )


async def test_dashboard_refreshes_sessions_concurrently_and_isolates_failures(
    database: Database,
) -> None:
    async with database.sessions.begin() as session:
        repository = AutomationRepository(session)
        runs = await repository.register_event(
            _event(),
            ("first-investigation", "second-investigation"),
        )
        for run, session_id in zip(
            runs,
            ("devin-completed", "devin-unavailable"),
            strict=True,
        ):
            assert await repository.claim_run(run.id) is True
            await repository.record_devin_session(
                run.id,
                session_id=session_id,
                status="running",
                status_detail="working",
            )

    requests_started = 0
    both_requests_started = asyncio.Event()

    async def handle_devin_request(request: httpx.Request) -> httpx.Response:
        nonlocal requests_started
        requests_started += 1
        if requests_started == 2:
            both_requests_started.set()
        await asyncio.wait_for(both_requests_started.wait(), timeout=1)

        session_id = request.url.path.rsplit("/", maxsplit=1)[-1]
        if session_id == "devin-unavailable":
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "session_id": session_id,
                "url": f"https://app.devin.ai/sessions/{session_id}",
                "status": "exit",
                "status_detail": "finished",
                "tags": ["github-automation", "bug-investigation"],
                "org_id": "org-test",
                "created_at": 1,
                "updated_at": 2,
                "acus_consumed": 1.0,
                "pull_requests": [],
            },
        )

    transport = httpx.MockTransport(handle_devin_request)
    async with DevinClient(
        "cog_test",
        base_url="https://api.devin.test/v3/",
        transport=transport,
    ) as client:
        dashboard = DashboardService()
        dashboard.configure(database, DevinSessions(client, "org-test"))
        snapshot = await dashboard.snapshot()

    assert requests_started == 2
    assert snapshot.metrics.completed == 1
    assert snapshot.metrics.in_progress == 1
    states_by_session = {run.devin_session_id: run.state for run in snapshot.runs}
    assert states_by_session == {
        "devin-completed": WorkflowRunState.COMPLETED,
        "devin-unavailable": WorkflowRunState.IN_PROGRESS,
    }


async def test_external_ids_are_scoped_to_trigger_source(
    database_session: AsyncSession,
) -> None:
    repository = AutomationRepository(database_session)
    external_id = uuid4().hex

    github_runs = await repository.register_event(
        _event(source="github", external_id=external_id),
        ("investigation",),
    )
    custom_runs = await repository.register_event(
        _event(source="custom-webhook", external_id=external_id),
        ("investigation",),
    )

    assert github_runs[0].trigger_event_id != custom_runs[0].trigger_event_id
