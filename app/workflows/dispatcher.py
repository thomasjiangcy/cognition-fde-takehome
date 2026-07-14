from collections.abc import Iterable, Sequence
from typing import Protocol

from app.github.webhooks.models import GitHubDelivery


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

    async def execute(
        self,
        workflows: Sequence[Workflow],
        delivery: GitHubDelivery,
    ) -> None:
        for workflow in workflows:
            await workflow.run(delivery)
