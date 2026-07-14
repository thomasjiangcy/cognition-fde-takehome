import sys
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from app.seeds import SEED_CATALOG
from scripts.seed_issues import (
    CreateIssueRequest,
    CreateLabelRequest,
    GitHubCliClient,
    GitHubClient,
    Repository,
    parse_arguments,
    seed_issue,
)

# These fixtures simulate only GitHub's network boundary. Their shapes follow:
# https://docs.github.com/en/rest/issues/issues#list-repository-issues
# https://docs.github.com/en/rest/issues/issues#create-an-issue
# https://docs.github.com/en/rest/issues/labels#get-a-label
# https://docs.github.com/en/rest/issues/labels#create-a-label
# https://cli.github.com/manual/gh_api


@pytest.mark.anyio
async def test_seed_creates_missing_label_and_issue() -> None:
    requested_paths: list[str] = []
    seed = SEED_CATALOG["mixed-chart-matrixify"]

    def github_handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
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

    assert result.issue_number == 1
    assert requested_paths == [
        "/repos/thomasjiangcy/superset/labels/validation:required",
        "/repos/thomasjiangcy/superset/labels",
        "/repos/thomasjiangcy/superset/labels/validation:validated",
        "/repos/thomasjiangcy/superset/labels",
        "/repos/thomasjiangcy/superset/labels/#bug:cant-reproduce",
        "/repos/thomasjiangcy/superset/labels",
        "/repos/thomasjiangcy/superset/labels/devin:assigned",
        "/repos/thomasjiangcy/superset/labels",
        "/repos/thomasjiangcy/superset/issues",
    ]


@pytest.mark.anyio
async def test_seed_uses_gh_api_contract(tmp_path: Path) -> None:
    executable = tmp_path / "gh"
    executable.write_text(
        f"""#!{sys.executable}
import json
import sys

arguments = sys.argv[1:]
method = arguments[arguments.index("--method") + 1]
path = next(argument for argument in arguments if argument.startswith("repos/"))
if method == "GET" and "/labels/" in path:
    raise SystemExit(1)
payload = json.load(sys.stdin)
if path.endswith("/issues"):
    payload.update({{"number": 3, "html_url": "https://github.com/thomasjiangcy/superset/issues/3"}})
print(json.dumps(payload))
""",
        encoding="utf-8",
    )
    executable.chmod(0o700)

    result = await seed_issue(
        GitHubCliClient(str(executable)),
        Repository.parse("thomasjiangcy/superset"),
        SEED_CATALOG["mixed-chart-matrixify"],
    )

    assert result.issue_number == 3
    assert result.issue_url == "https://github.com/thomasjiangcy/superset/issues/3"


def test_seed_body_contains_no_seeder_metadata() -> None:
    seed = SEED_CATALOG["mixed-chart-matrixify"]

    body = seed.render_body()

    assert body.startswith("### Bug description\n\nHello,")
    assert "Upstream report:" not in body
    assert "<!-- cognition-fde-seed:" not in body


def test_parse_arguments_selects_single_issue() -> None:
    arguments = parse_arguments(
        ["mixed-chart-matrixify", "--repo", "thomasjiangcy/superset"],
    )

    assert arguments.repository.full_name == "thomasjiangcy/superset"
    assert len(arguments.issues) == 1
    assert arguments.issues[0].key == "apache-superset-39007"


def test_parse_arguments_selects_all_issues() -> None:
    arguments = parse_arguments(
        ["--all", "--repo", "thomasjiangcy/superset"],
    )

    assert arguments.repository.full_name == "thomasjiangcy/superset"
    assert len(arguments.issues) == len(SEED_CATALOG)
    assert {issue.key for issue in arguments.issues} == {
        "apache-superset-39007",
        "apache-superset-40708",
    }


def test_parse_arguments_all_positional_is_synonym_for_flag() -> None:
    arguments = parse_arguments(
        ["all", "--repo", "thomasjiangcy/superset"],
    )

    assert arguments.repository.full_name == "thomasjiangcy/superset"
    assert len(arguments.issues) == len(SEED_CATALOG)
