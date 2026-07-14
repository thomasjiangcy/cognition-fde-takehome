import logging
from collections.abc import Iterable, Sequence
from typing import Protocol

from app.webhooks.github.models import GitHubDelivery

logger = logging.getLogger(__name__)


class Workflow(Protocol):
    """Contract implemented by webhook-triggered workflows."""

    name: str

    def matches(self, delivery: GitHubDelivery) -> bool: ...

    async def run(self, delivery: GitHubDelivery) -> None: ...


class WorkflowDispatcher:
    """Select and execute workflows for a normalized GitHub delivery."""

    def __init__(self, workflows: Iterable[Workflow] = ()) -> None:
        self._workflows = tuple(workflows)

    def select(self, delivery: GitHubDelivery) -> tuple[Workflow, ...]:
        return tuple(
            workflow for workflow in self._workflows if workflow.matches(delivery)
        )

    async def dispatch(self, delivery: GitHubDelivery) -> None:
        await self.execute(self.select(delivery), delivery)

    async def execute(
        self,
        workflows: Sequence[Workflow],
        delivery: GitHubDelivery,
    ) -> None:
        for workflow in workflows:
            try:
                logger.info(
                    "Executing workflow",
                    extra={
                        "workflow_name": workflow.name,
                        "github_delivery_id": delivery.delivery_id,
                    },
                )
                await workflow.run(delivery)
            except Exception:
                logger.exception(
                    "Workflow execution failed",
                    extra={
                        "workflow_name": workflow.name,
                        "github_delivery_id": delivery.delivery_id,
                    },
                )
