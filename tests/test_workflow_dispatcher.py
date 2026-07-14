import httpx
import pytest

from app.devin.client import DevinClient
from app.devin.sessions import DevinSessions
from app.webhooks.github.models import (
    GitHubDelivery,
    GitHubIssue,
    GitHubIssuesPayload,
    GitHubRepository,
    GitHubUser,
)
from app.workflows.bug_investigation import BugInvestigationWorkflow
from app.workflows.dispatcher import WorkflowDispatcher


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


def _unexpected_request(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"Unexpected Devin request: {request.method} {request.url}")


@pytest.mark.anyio
async def test_selects_opened_issue_with_bug_description() -> None:
    transport = httpx.MockTransport(_unexpected_request)
    async with DevinClient("cog_test", transport=transport) as client:
        workflow = BugInvestigationWorkflow(
            DevinSessions(client, "org-test"),
            "playbook-bug-investigation",
        )
        dispatcher = WorkflowDispatcher([workflow])
        delivery = _issues_delivery(
            "### Bug description\n\nThe dimension only applies to Query A."
        )

        assert dispatcher.select(delivery) == (workflow,)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "delivery",
    [
        _issues_delivery("The dimension only applies to Query A."),
        _issues_delivery(None),
        _issues_delivery("### Bug description", action="edited"),
    ],
)
async def test_does_not_select_non_matching_issue(delivery: GitHubDelivery) -> None:
    transport = httpx.MockTransport(_unexpected_request)
    async with DevinClient("cog_test", transport=transport) as client:
        workflow = BugInvestigationWorkflow(
            DevinSessions(client, "org-test"),
            "playbook-bug-investigation",
        )
        dispatcher = WorkflowDispatcher([workflow])

        assert dispatcher.select(delivery) == ()
