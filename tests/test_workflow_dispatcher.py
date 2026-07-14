import pytest

from app.webhooks.github.models import GitHubDelivery
from app.workflows.dispatcher import WorkflowDispatcher
from app.workflows.initial_workflow import InitialWorkflow


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_placeholder_workflow_is_not_selected() -> None:
    dispatcher = WorkflowDispatcher([InitialWorkflow()])
    delivery = GitHubDelivery(
        delivery_id="delivery-id",
        event="issues",
        action="opened",
        repository="owner/repository",
        payload={},
    )

    workflows = dispatcher.select(delivery)
    await dispatcher.execute(workflows, delivery)

    assert workflows == ()
