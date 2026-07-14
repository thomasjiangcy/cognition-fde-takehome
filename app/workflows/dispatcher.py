import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.automation.models import WorkflowRunState
from app.automation.repository import AutomationRepository, TriggerEventData
from app.database import Database
from app.webhooks.github.models import GitHubDelivery

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    devin_session_id: str
    devin_status: str
    devin_status_detail: str | None


class Workflow(Protocol):
    """Contract implemented by webhook-triggered workflows."""

    name: str

    def matches(self, delivery: GitHubDelivery) -> bool: ...

    async def run(self, delivery: GitHubDelivery) -> WorkflowResult: ...


@dataclass(frozen=True, slots=True)
class PreparedWorkflow:
    run_id: UUID
    workflow: Workflow


class WorkflowDispatcher:
    """Persist, select, and execute workflows for normalized deliveries."""

    def __init__(self, workflows: Iterable[Workflow] = ()) -> None:
        self._database: Database | None = None
        self._workflows = tuple(workflows)

    def configure(self, database: Database, workflows: Iterable[Workflow]) -> None:
        self._database = database
        self._workflows = tuple(workflows)

    def select(self, delivery: GitHubDelivery) -> tuple[Workflow, ...]:
        return tuple(
            workflow for workflow in self._workflows if workflow.matches(delivery)
        )

    async def prepare(
        self,
        delivery: GitHubDelivery,
        event: TriggerEventData,
    ) -> tuple[PreparedWorkflow, ...]:
        database = self._require_database()
        workflows = self.select(delivery)
        async with database.sessions.begin() as session:
            runs = await AutomationRepository(session).register_event(
                event,
                tuple(workflow.name for workflow in workflows),
            )

        runs_by_name = {run.workflow_name: run for run in runs}
        return tuple(
            PreparedWorkflow(
                run_id=runs_by_name[workflow.name].id,
                workflow=workflow,
            )
            for workflow in workflows
            if runs_by_name[workflow.name].state is WorkflowRunState.QUEUED
            and runs_by_name[workflow.name].devin_session_id is None
        )

    async def execute(
        self,
        prepared_workflows: Sequence[PreparedWorkflow],
        delivery: GitHubDelivery,
    ) -> list[WorkflowResult]:
        database = self._require_database()
        results: list[WorkflowResult] = []
        for prepared in prepared_workflows:
            try:
                logger.info(
                    "Executing workflow",
                    extra={
                        "workflow_name": prepared.workflow.name,
                        "github_delivery_id": delivery.delivery_id,
                    },
                )
                async with database.sessions.begin() as session:
                    claimed = await AutomationRepository(session).claim_run(
                        prepared.run_id
                    )
                if not claimed:
                    continue

                result = await prepared.workflow.run(delivery)
                results.append(result)
                async with database.sessions.begin() as session:
                    await AutomationRepository(session).record_devin_session(
                        prepared.run_id,
                        session_id=result.devin_session_id,
                        status=result.devin_status,
                        status_detail=result.devin_status_detail,
                    )
            except Exception as error:
                logger.exception(
                    "Workflow execution failed",
                    extra={
                        "workflow_name": prepared.workflow.name,
                        "github_delivery_id": delivery.delivery_id,
                    },
                )
                async with database.sessions.begin() as session:
                    await AutomationRepository(session).mark_failed(
                        prepared.run_id,
                        type(error).__name__,
                    )
        return results

    def _require_database(self) -> Database:
        if self._database is None:
            raise RuntimeError("Workflow dispatcher is not configured")
        return self._database
