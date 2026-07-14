import logging

import pytest

from app.webhooks.github.models import (
    GitHubDelivery,
    GitHubIssue,
    GitHubIssuesPayload,
    GitHubRepository,
    GitHubUser,
)
from app.workflows.dispatcher import WorkflowDispatcher
from app.workflows.initial_workflow import BugInvestigationWorkflow


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _issues_delivery(
    body: str | None,
    *,
    action: str = "opened",
) -> GitHubDelivery:
    payload = GitHubIssuesPayload(
        action=action,
        issue=GitHubIssue(
            number=1347,
            title="Mixed Chart matrixify does not apply to Query B",
            body=body,
            state="open",
            html_url="https://github.com/octocat/superset/issues/1347",
            user=GitHubUser(login="octocat"),
            labels=[],
        ),
        repository=GitHubRepository(full_name="octocat/superset"),
        sender=GitHubUser(login="octocat"),
    )
    return GitHubDelivery(
        delivery_id="delivery-id",
        event="issues",
        action=action,
        repository=payload.repository.full_name,
        payload=payload,
    )


@pytest.mark.anyio
async def test_dispatches_opened_issue_with_bug_description(
    caplog: pytest.LogCaptureFixture,
) -> None:
    workflow = BugInvestigationWorkflow()
    dispatcher = WorkflowDispatcher([workflow])
    delivery = _issues_delivery(
        "### Bug description\n\nThe dimension only applies to Query A."
    )
    caplog.set_level(logging.INFO, logger="app.workflows.dispatcher")

    selected = dispatcher.select(delivery)
    await dispatcher.dispatch(delivery)

    assert selected == (workflow,)
    assert (
        "app.workflows.dispatcher",
        logging.INFO,
        "Executing workflow",
    ) in caplog.record_tuples


@pytest.mark.parametrize(
    "delivery",
    [
        _issues_delivery("The dimension only applies to Query A."),
        _issues_delivery(None),
        _issues_delivery("### Bug description", action="edited"),
    ],
)
def test_does_not_select_non_matching_issue(delivery: GitHubDelivery) -> None:
    dispatcher = WorkflowDispatcher([BugInvestigationWorkflow()])

    assert dispatcher.select(delivery) == ()
