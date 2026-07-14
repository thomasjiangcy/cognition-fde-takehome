import pytest

from app.github.webhooks.models import GitHubDelivery
from app.workflows.dispatcher import WorkflowDispatcher


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class MatchingWorkflow:
    name = "matching-workflow"

    def __init__(self) -> None:
        self.ran = False

    def matches(self, delivery: GitHubDelivery) -> bool:
        return delivery.event == "issues"

    async def run(self, delivery: GitHubDelivery) -> None:
        self.ran = True


class NonMatchingWorkflow:
    name = "non-matching-workflow"

    def matches(self, delivery: GitHubDelivery) -> bool:
        return False

    async def run(self, delivery: GitHubDelivery) -> None:
        raise AssertionError("A non-matching workflow must not run")


@pytest.mark.anyio
async def test_dispatcher_selects_and_executes_matching_workflows() -> None:
    matching_workflow = MatchingWorkflow()
    dispatcher = WorkflowDispatcher([NonMatchingWorkflow(), matching_workflow])
    delivery = GitHubDelivery(
        delivery_id="delivery-id",
        event="issues",
        action="opened",
        repository="owner/repository",
        payload={},
    )

    workflows = dispatcher.select(delivery)
    await dispatcher.execute(workflows, delivery)

    assert [workflow.name for workflow in workflows] == ["matching-workflow"]
    assert matching_workflow.ran
