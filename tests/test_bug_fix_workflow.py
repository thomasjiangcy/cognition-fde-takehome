import httpx
import pytest
from pydantic import AnyHttpUrl, SecretStr

from app.devin.client import DevinClient
from app.devin.models import DevinSession, DevinSessionStatus, DevinSessionStatusDetail
from app.devin.sessions import DevinSessions
from app.github.client import GitHubClient
from app.webhooks.github.models import (
    GitHubDelivery,
    GitHubIssue,
    GitHubIssueLabel,
    GitHubIssuesPayload,
    GitHubRepository,
    GitHubUser,
)
from app.workflows.bug_fix import BugFixWorkflow

# These tests cover the GitHub and Devin API boundaries. The GitHub client is
# exercised with a mocked httpx transport, and the Devin sessions client is
# exercised with a mocked DevinClient transport.


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _unexpected_request(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"Unexpected request: {request.method} {request.url}")


def _manual_delivery(
    labels: list[GitHubIssueLabel],
    *,
    issue_number: int = 42,
) -> GitHubDelivery:
    payload = GitHubIssuesPayload(
        action="manual",
        issue=GitHubIssue(
            number=issue_number,
            title="Dashboard label colors intermittently fallback",
            body="### Bug description\n\nIntermittent fallback.",
            state="open",
            html_url=f"https://github.com/octocat/superset/issues/{issue_number}",
            user=GitHubUser(login="octocat"),
            labels=labels,
        ),
        repository=GitHubRepository(full_name="octocat/superset"),
        sender=GitHubUser(login="octocat"),
    )
    return GitHubDelivery(
        delivery_id="manual-42",
        event="manual",
        action=None,
        repository=payload.repository.full_name,
        payload=payload,
    )


def _validated_labels() -> list[GitHubIssueLabel]:
    return [GitHubIssueLabel(name="validation:validated")]


def _validated_and_assigned_labels() -> list[GitHubIssueLabel]:
    return [
        GitHubIssueLabel(name="validation:validated"),
        GitHubIssueLabel(name="devin:assigned"),
    ]


@pytest.mark.anyio
async def test_bug_fix_workflow_matches_validated_unassigned_issue() -> None:
    workflow = BugFixWorkflow(
        DevinSessions(
            DevinClient("cog_test", transport=httpx.MockTransport(_unexpected_request)),
            "org-test",
        ),
        GitHubClient(
            SecretStr("test"), transport=httpx.MockTransport(_unexpected_request)
        ),
        "playbook-bug-fix",
    )

    assert workflow.matches(_manual_delivery(_validated_labels())) is True
    assert workflow.matches(_manual_delivery(_validated_and_assigned_labels())) is False


@pytest.mark.anyio
async def test_bug_fix_workflow_does_not_match_webhook_delivery() -> None:
    workflow = BugFixWorkflow(
        DevinSessions(
            DevinClient("cog_test", transport=httpx.MockTransport(_unexpected_request)),
            "org-test",
        ),
        GitHubClient(
            SecretStr("test"), transport=httpx.MockTransport(_unexpected_request)
        ),
        "playbook-bug-fix",
    )
    payload = GitHubIssuesPayload(
        action="opened",
        issue=GitHubIssue(
            number=42,
            title="Bug",
            body="### Bug description\n\nBug",
            state="open",
            html_url="https://github.com/octocat/superset/issues/42",
            user=GitHubUser(login="octocat"),
            labels=_validated_labels(),
        ),
        repository=GitHubRepository(full_name="octocat/superset"),
        sender=GitHubUser(login="octocat"),
    )
    delivery = GitHubDelivery(
        delivery_id="webhook-42",
        event="issues",
        action="opened",
        repository=payload.repository.full_name,
        payload=payload,
    )

    assert workflow.matches(delivery) is False


@pytest.mark.anyio
async def test_bug_fix_workflow_adds_label_and_creates_session() -> None:
    github_requests: list[tuple[str, str]] = []
    devin_requests: list[tuple[str, str]] = []

    def handle_github(request: httpx.Request) -> httpx.Response:
        github_requests.append((request.method, request.url.path))
        if request.method == "GET" and "/labels/" in request.url.path:
            return httpx.Response(404, json={"message": "Not Found"})
        if request.method == "POST" and request.url.path.endswith("/issues/42/labels"):
            return httpx.Response(200, json=[{"name": "devin:assigned"}])
        if request.method == "POST" and request.url.path.endswith("/labels"):
            return httpx.Response(201, content=request.content)
        return httpx.Response(500)

    def handle_devin(request: httpx.Request) -> httpx.Response:
        devin_requests.append((request.method, request.url.path))
        session = DevinSession(
            session_id="devin-fix-42",
            url=AnyHttpUrl("https://app.devin.ai/sessions/devin-fix-42"),
            status=DevinSessionStatus.RUNNING,
            status_detail=DevinSessionStatusDetail.WAITING_FOR_USER,
            structured_output=None,
            tags=["github-automation", "bug-fix"],
            org_id="org-test",
            created_at=1,
            updated_at=1,
            acus_consumed=0.0,
        )
        return httpx.Response(200, content=session.model_dump_json().encode())

    github_transport = httpx.MockTransport(handle_github)
    devin_transport = httpx.MockTransport(handle_devin)
    async with (
        GitHubClient(
            SecretStr("test-token"), transport=github_transport
        ) as github_client,
        DevinClient("cog_test", transport=devin_transport) as devin_client,
    ):
        workflow = BugFixWorkflow(
            DevinSessions(devin_client, "org-test"),
            github_client,
            "playbook-bug-fix",
        )
        result = await workflow.run(_manual_delivery(_validated_labels()))

    assert result.devin_session_id == "devin-fix-42"
    assert any("/labels/devin:assigned" in path for _, path in github_requests)
    assert any("/issues/42/labels" in path for _, path in github_requests)
    assert devin_requests == [("POST", "/v3/organizations/org-test/sessions")]
