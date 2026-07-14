import httpx
import pytest
from pydantic import SecretStr

from scripts.seed_issues import (
    SEED_CATALOG,
    CreateIssueRequest,
    CreateLabelRequest,
    GitHubClient,
    Repository,
    seed_issue,
)

# These fixtures simulate only GitHub's network boundary. Their shapes follow:
# https://docs.github.com/en/rest/issues/issues#list-repository-issues
# https://docs.github.com/en/rest/issues/issues#create-an-issue
# https://docs.github.com/en/rest/issues/labels#get-a-label
# https://docs.github.com/en/rest/issues/labels#create-a-label


@pytest.mark.anyio
async def test_seed_creates_missing_label_and_issue() -> None:
    requested_paths: list[str] = []
    seed = SEED_CATALOG["mixed-chart-matrixify"]

    def github_handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.method == "GET" and request.url.path.endswith("/issues"):
            assert request.url.params["state"] == "open"
            return httpx.Response(200, json=[])
        if request.method == "GET" and "/labels/" in request.url.path:
            return httpx.Response(404, json={"message": "Not Found"})
        if request.method == "POST" and request.url.path.endswith("/labels"):
            label = CreateLabelRequest.model_validate_json(
                request.content,
                strict=True,
            )
            return httpx.Response(201, content=label.model_dump_json())
        if request.method == "POST" and request.url.path.endswith("/issues"):
            issue = CreateIssueRequest.model_validate_json(
                request.content,
                strict=True,
            )
            assert issue.labels == ("validation:required",)
            assert issue.title == seed.title
            assert issue.body == seed.render_body()
            return httpx.Response(
                201,
                json={
                    "number": 1,
                    "title": issue.title,
                    "body": issue.body,
                    "html_url": "https://github.com/thomasjiangcy/superset/issues/1",
                },
            )
        return httpx.Response(500, json={"message": "Unexpected request"})

    transport = httpx.MockTransport(github_handler)
    async with GitHubClient(
        SecretStr("test-token"),
        base_url="https://api.github.test/",
        transport=transport,
    ) as client:
        result = await seed_issue(
            client,
            Repository.parse("thomasjiangcy/superset"),
            seed,
        )

    assert result.created is True
    assert result.issue_number == 1
    assert requested_paths == [
        "/repos/thomasjiangcy/superset/issues",
        "/repos/thomasjiangcy/superset/labels/validation:required",
        "/repos/thomasjiangcy/superset/labels",
        "/repos/thomasjiangcy/superset/issues",
    ]


@pytest.mark.anyio
async def test_seed_reuses_open_issue_with_exact_content() -> None:
    seed = SEED_CATALOG["mixed-chart-matrixify"]
    request_count = 0

    def github_handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            200,
            json=[
                {
                    "number": 7,
                    "title": seed.title,
                    "body": seed.render_body(),
                    "html_url": "https://github.com/thomasjiangcy/superset/issues/7",
                },
            ],
        )

    transport = httpx.MockTransport(github_handler)
    async with GitHubClient(
        SecretStr("test-token"),
        base_url="https://api.github.test/",
        transport=transport,
    ) as client:
        result = await seed_issue(
            client,
            Repository.parse("thomasjiangcy/superset"),
            seed,
        )

    assert result.created is False
    assert result.issue_number == 7
    assert request_count == 1


def test_seed_body_contains_no_seeder_metadata() -> None:
    seed = SEED_CATALOG["mixed-chart-matrixify"]

    body = seed.render_body()

    assert body.startswith("### Bug description\n\nHello,")
    assert "Upstream report:" not in body
    assert "<!-- cognition-fde-seed:" not in body
