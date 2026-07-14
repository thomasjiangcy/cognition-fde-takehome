from uuid import UUID

from pydantic import AnyHttpUrl, AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.models import TriggerEvent, WorkflowRun, WorkflowRunState


class TriggerEventData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source: str = Field(min_length=1, max_length=64)
    external_id: str = Field(min_length=1, max_length=255)
    event_type: str = Field(min_length=1, max_length=128)
    action: str | None = Field(default=None, min_length=1, max_length=128)
    subject_type: str | None = Field(default=None, min_length=1, max_length=64)
    subject_id: str | None = Field(default=None, min_length=1, max_length=255)
    subject_title: str | None = None
    subject_url: AnyHttpUrl | None = None
    received_at: AwareDatetime


class AutomationRepository:
    """Persist trigger events and workflow runs in the caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register_event(
        self,
        event: TriggerEventData,
        workflow_names: tuple[str, ...],
    ) -> tuple[WorkflowRun, ...]:
        event_id = await self._ensure_event(event)
        unique_workflow_names = tuple(dict.fromkeys(workflow_names))
        for workflow_name in unique_workflow_names:
            await self._session.execute(
                insert(WorkflowRun)
                .values(
                    trigger_event_id=event_id,
                    workflow_name=workflow_name,
                )
                .on_conflict_do_nothing(
                    constraint="uq_workflow_runs_trigger_event_id_workflow_name"
                )
            )

        if not unique_workflow_names:
            return ()

        result = await self._session.scalars(
            select(WorkflowRun).where(
                WorkflowRun.trigger_event_id == event_id,
                WorkflowRun.workflow_name.in_(unique_workflow_names),
            )
        )
        runs_by_name = {run.workflow_name: run for run in result}
        return tuple(runs_by_name[name] for name in unique_workflow_names)

    async def claim_run(self, run_id: UUID) -> bool:
        result = await self._session.execute(
            update(WorkflowRun)
            .where(
                WorkflowRun.id == run_id,
                WorkflowRun.state == WorkflowRunState.QUEUED,
            )
            .values(
                state=WorkflowRunState.IN_PROGRESS,
                failure_reason=None,
                updated_at=func.now(),
            )
            .returning(WorkflowRun.id)
        )
        return result.scalar_one_or_none() is not None

    async def record_devin_session(
        self,
        run_id: UUID,
        *,
        session_id: str,
        status: str,
        status_detail: str | None,
    ) -> None:
        await self._session.execute(
            update(WorkflowRun)
            .where(WorkflowRun.id == run_id)
            .values(
                devin_session_id=session_id,
                devin_status=status,
                devin_status_detail=status_detail,
                updated_at=func.now(),
            )
        )

    async def update_devin_status(
        self,
        run_id: UUID,
        *,
        state: WorkflowRunState,
        status: str,
        status_detail: str | None,
    ) -> None:
        await self._session.execute(
            update(WorkflowRun)
            .where(WorkflowRun.id == run_id)
            .values(
                state=state,
                devin_status=status,
                devin_status_detail=status_detail,
                last_status_sync_at=func.now(),
                updated_at=func.now(),
            )
        )

    async def mark_failed(self, run_id: UUID, reason: str) -> None:
        await self._session.execute(
            update(WorkflowRun)
            .where(WorkflowRun.id == run_id)
            .values(
                state=WorkflowRunState.FAILED,
                failure_reason=reason,
                updated_at=func.now(),
            )
        )

    async def _ensure_event(self, event: TriggerEventData) -> UUID:
        result = await self._session.execute(
            insert(TriggerEvent)
            .values(
                source=event.source,
                external_id=event.external_id,
                event_type=event.event_type,
                action=event.action,
                subject_type=event.subject_type,
                subject_id=event.subject_id,
                subject_title=event.subject_title,
                subject_url=(
                    str(event.subject_url) if event.subject_url is not None else None
                ),
                received_at=event.received_at,
            )
            .on_conflict_do_nothing(constraint="uq_trigger_events_source_external_id")
            .returning(TriggerEvent.id)
        )
        event_id = result.scalar_one_or_none()
        if event_id is not None:
            return event_id

        return (
            await self._session.scalars(
                select(TriggerEvent.id).where(
                    TriggerEvent.source == event.source,
                    TriggerEvent.external_id == event.external_id,
                )
            )
        ).one()
