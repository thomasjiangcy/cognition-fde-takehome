from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import AnyHttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.models import WorkflowRunState
from app.automation.repository import AutomationRepository, TriggerEventData
from app.database import Database

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
