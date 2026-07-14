import json

import httpx
import pytest
from pydantic import SecretStr

from app.github.client import GitHubClient
from app.github.models import GitHubLabelDefinition

# These simulations cover the third-party GitHub REST API boundary:
# List issues: https://docs.github.com/en/rest/issues/issues#list-repository-issues
# Get a label: https://docs.github.com/en/rest/issues/labels#get-a-label
# Create a label: https://docs.github.com/en/rest/issues/labels#create-a-label
# Add labels to an issue: https://docs.github.com/en/rest/issues/labels#add-labels-to-an-issue


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _issues_response() -> list[dict]:
    return [
        {
            "number": 1,
            "title": "Issue one",
            "body": "### Bug description\n\nOne",
            "state": "open",
            "html_url": "https://github.com/octocat/superset/issues/1",
            "user": {"login": "octocat"},
            "labels": [
                {"name": "validation:validated"},
                {"name": "dashboard:colors"},
            ],
        },
        {
            "number": 2,
            "title": "Issue two",
            "body": "### Bug description\n\nTwo",
            "state": "open",
            "html_url": "https://github.com/octocat/superset/issues/2",
            "user": {"login": "octocat"},
            "labels": [
                {"name": "validation:validated"},
                {"name": "devin:assigned"},
            ],
        },
    ]


@pytest.mark.anyio
async def test_list_issues_returns_validated_issues() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/octocat/superset/issues"
        assert request.url.params["labels"] == "validation:validated"
        assert request.url.params["state"] == "open"
        return httpx.Response(200, json=_issues_response())

    transport = httpx.MockTransport(handler)
    async with GitHubClient(SecretStr("test-token"), transport=transport) as client:
        issues = await client.list_issues(
            "octocat/superset",
            labels=("validation:validated",),
        )

    assert len(issues) == 2
    assert issues[0].number == 1
    assert issues[0].labels[0].name == "validation:validated"


@pytest.mark.anyio
async def test_ensure_label_creates_missing_label() -> None:
    requested: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(404, json={"message": "Not Found"})
        if request.method == "POST":
            return httpx.Response(201, content=request.content)
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    async with GitHubClient(SecretStr("test-token"), transport=transport) as client:
        label = await client.ensure_label(
            "octocat/superset",
            GitHubLabelDefinition(
                name="devin:assigned",
                color="0E8A16",
                description="A Devin session has been assigned",
            ),
        )

    assert requested == [
        ("GET", "/repos/octocat/superset/labels/devin:assigned"),
        ("POST", "/repos/octocat/superset/labels"),
    ]
    assert label.name == "devin:assigned"


@pytest.mark.anyio
async def test_add_label_posts_labels_to_issue() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/octocat/superset/issues/42/labels"
        assert json.loads(request.content) == {"labels": ["devin:assigned"]}
        return httpx.Response(200, json=[{"name": "devin:assigned"}])

    transport = httpx.MockTransport(handler)
    async with GitHubClient(SecretStr("test-token"), transport=transport) as client:
        await client.add_label("octocat/superset", 42, "devin:assigned")
