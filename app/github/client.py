from __future__ import annotations

import httpx
from pydantic import SecretStr

from app.github.models import GitHubLabel, GitHubLabelDefinition
from app.webhooks.github.models import GitHubIssue

GITHUB_API_VERSION = "2022-11-28"


def _label_path(repository: str, label_name: str) -> str:
    from urllib.parse import quote

    return f"repos/{repository}/labels/{quote(label_name, safe='')}"


class GitHubClient:
    """Minimal async client for the GitHub Issues and Labels REST APIs."""

    def __init__(
        self,
        token: SecretStr,
        *,
        base_url: str = "https://api.github.com/",
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_seconds,
            transport=transport,
            headers={
                "Authorization": f"Bearer {token.get_secret_value()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
            },
        )

    async def list_issues(
        self,
        repository: str,
        labels: tuple[str, ...],
        *,
        state: str = "open",
    ) -> list[GitHubIssue]:
        """Return issues matching any of the provided labels.

        Callers are responsible for filtering out issues that also carry an
        unwanted label; GitHub's issue list endpoint returns an OR match for the
        supplied labels.
        """
        response = await self._http.get(
            f"repos/{repository}/issues",
            params={
                "state": state,
                "labels": ",".join(labels),
                "per_page": "100",
            },
        )
        response.raise_for_status()
        return [GitHubIssue.model_validate(item) for item in response.json()]

    async def ensure_label(
        self,
        repository: str,
        label: GitHubLabelDefinition,
    ) -> GitHubLabel:
        """Ensure a repository label exists, creating it if necessary."""
        response = await self._http.get(_label_path(repository, label.name))
        if response.status_code == httpx.codes.NOT_FOUND:
            response = await self._http.post(
                f"repos/{repository}/labels",
                content=label.model_dump_json(),
                headers={"Content-Type": "application/json"},
            )
        response.raise_for_status()
        return GitHubLabel.model_validate_json(response.content)

    async def add_label(
        self,
        repository: str,
        issue_number: int,
        label_name: str,
    ) -> None:
        """Add an existing label to an issue."""
        response = await self._http.post(
            f"repos/{repository}/issues/{issue_number}/labels",
            json={"labels": [label_name]},
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None:
        await self._http.aclose()
