import httpx
import pytest
from pydantic import ValidationError

from app.devin.client import DevinClient
from app.devin.models import DevinSessionCreateRequest
from app.devin.sessions import DevinSessions
from app.webhooks.github.models import (
    GitHubDelivery,
    GitHubIssue,
    GitHubIssuesPayload,
    GitHubRepository,
    GitHubUser,
)
from app.workflows.bug_investigation import BugInvestigationWorkflow

# Simulates Devin's documented organization create-session endpoint and schema:
# https://docs.devin.ai/api-reference/v3/sessions/post-organizations-sessions


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_bug_investigation_starts_devin_session_with_issue_context() -> None:
    received_requests: list[DevinSessionCreateRequest] = []

    def handle_devin_request(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v3/organizations/org-test/sessions"
        received_requests.append(
            DevinSessionCreateRequest.model_validate_json(request.content)
        )
        return httpx.Response(
            200,
            json={
                "session_id": "devin-investigation",
                "url": "https://app.devin.ai/sessions/devin-investigation",
                "status": "running",
                "status_detail": "working",
                "tags": ["github-automation", "bug-investigation"],
                "org_id": "org-test",
                "created_at": 1,
                "updated_at": 1,
                "acus_consumed": 0.0,
                "pull_requests": [],
            },
        )

    payload = GitHubIssuesPayload(
        action="opened",
        issue=GitHubIssue(
            number=1347,
            title="Mixed Chart matrixify does not apply to Query B",
            body="### Bug description\n\nThe dimension only applies to Query A.",
            state="open",
            html_url="https://github.com/octocat/superset/issues/1347",
            user=GitHubUser(login="octocat"),
            labels=[],
        ),
        repository=GitHubRepository(full_name="octocat/superset"),
        sender=GitHubUser(login="octocat"),
    )
    delivery = GitHubDelivery(
        delivery_id="delivery-id",
        event="issues",
        action="opened",
        repository=payload.repository.full_name,
        payload=payload,
    )
    transport = httpx.MockTransport(handle_devin_request)
    async with DevinClient(
        "cog_test",
        base_url="https://api.devin.test/v3/",
        transport=transport,
    ) as client:
        workflow = BugInvestigationWorkflow(
            DevinSessions(client, "org-test"),
            "playbook-bug-investigation",
        )

        result = await workflow.run(delivery)

    assert result.devin_session_id == "devin-investigation"
    assert result.devin_status == "running"
    assert result.devin_status_detail == "working"
    assert len(received_requests) == 1
    request = received_requests[0]
    assert request.playbook_id == "playbook-bug-investigation"
    assert request.repos == ["octocat/superset"]
    assert request.structured_output_required is True
    assert request.structured_output_schema is not None
    assert request.structured_output_schema["type"] == "object"
    properties = request.structured_output_schema["properties"]
    assert isinstance(properties, dict)
    assert "outcome" in properties
    assert request.tags == ["github-automation", "bug-investigation"]
    assert "Repository: octocat/superset" in request.prompt
    assert "Issue: https://github.com/octocat/superset/issues/1347" in request.prompt


def test_session_request_rejects_required_without_schema() -> None:
    with pytest.raises(ValidationError, match="structured_output_schema"):
        DevinSessionCreateRequest(
            prompt="Investigate a bug.",
            playbook_id="playbook-test",
            repos=["octocat/superset"],
            structured_output_required=True,
            tags=["test"],
            title="Test",
        )


def test_session_request_allows_optional_without_schema() -> None:
    request = DevinSessionCreateRequest(
        prompt="Investigate a bug.",
        playbook_id="playbook-test",
        repos=["octocat/superset"],
        structured_output_schema=None,
        structured_output_required=False,
        tags=["test"],
        title="Test",
    )
    assert request.structured_output_required is False
    assert request.structured_output_schema is None


@pytest.mark.anyio
async def test_devin_sessions_terminates_running_session() -> None:
    received: list[httpx.Request] = []

    def handle_devin_request(request: httpx.Request) -> httpx.Response:
        received.append(request)
        if request.method == "DELETE":
            assert request.url.path == "/v3/organizations/org-test/sessions/devin-123"
            assert request.url.query == b"archive=false"
            return httpx.Response(
                200,
                json={
                    "session_id": "devin-123",
                    "url": "https://app.devin.ai/sessions/devin-123",
                    "status": "running",
                    "status_detail": None,
                    "tags": ["github-automation", "bug-investigation"],
                    "org_id": "org-test",
                    "created_at": 1,
                    "updated_at": 2,
                    "acus_consumed": 1.0,
                    "pull_requests": [],
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handle_devin_request)
    async with DevinClient(
        "cog_test",
        base_url="https://api.devin.test/v3/",
        transport=transport,
    ) as client:
        await DevinSessions(client, "org-test").terminate("devin-123")

    assert len(received) == 1
    assert received[0].method == "DELETE"
