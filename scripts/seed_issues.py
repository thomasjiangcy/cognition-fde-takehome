from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, TypeAdapter
from pydantic_settings import BaseSettings, SettingsConfigDict

GITHUB_API_VERSION = "2022-11-28"
SEEDS_DIRECTORY = Path(__file__).with_name("seeds")


class GitHubSettings(BaseSettings):
    """Authentication used only when applying a seed to GitHub."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        strict=True,
    )

    github_token: SecretStr = Field(min_length=1)


class Repository(BaseModel):
    """Validated GitHub owner and repository name."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    owner: str = Field(pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
    name: str = Field(pattern=r"^[A-Za-z0-9._-]+$")

    @classmethod
    def parse(cls, value: str) -> Self:
        parts = value.split("/")
        if len(parts) != 2:
            raise ValueError("repository must use the OWNER/REPOSITORY format")
        return cls(owner=parts[0], name=parts[1])

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


class GitHubIssue(BaseModel):
    """Fields consumed from GitHub's issue response."""

    model_config = ConfigDict(extra="ignore", strict=True)

    number: int
    title: str
    body: str | None
    html_url: str = Field(pattern=r"^https://github\.com/.+")


class GitHubLabel(BaseModel):
    """Fields consumed from GitHub's label response."""

    model_config = ConfigDict(extra="ignore", strict=True)

    name: str
    color: str = Field(pattern=r"^[0-9A-Fa-f]{6}$")
    description: str | None


class CreateIssueRequest(BaseModel):
    """Documented GitHub create-issue request fields used by the seeder."""

    model_config = ConfigDict(extra="forbid", strict=True)

    title: str
    body: str
    labels: tuple[str, ...]


class CreateLabelRequest(BaseModel):
    """Documented GitHub create-label request fields used by the seeder."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    color: str = Field(pattern=r"^[0-9A-Fa-f]{6}$")
    description: str


@dataclass(frozen=True)
class SeedLabel:
    name: str
    color: str
    description: str


@dataclass(frozen=True)
class SeedIssue:
    key: str
    title: str
    source_url: str
    body_path: Path
    labels: tuple[SeedLabel, ...]

    @property
    def marker(self) -> str:
        return f"<!-- cognition-fde-seed:{self.key} -->"

    def render_body(self) -> str:
        report = self.body_path.read_text(encoding="utf-8").rstrip()
        return (
            f"{report}\n\n---\n\nUpstream report: {self.source_url}\n\n{self.marker}\n"
        )


SEED_CATALOG: dict[str, SeedIssue] = {
    "mixed-chart-matrixify": SeedIssue(
        key="apache-superset-39007",
        title="6.1.0rc1 - matrixify not applying to query B in Mixed Chart",
        source_url="https://github.com/apache/superset/issues/39007",
        body_path=SEEDS_DIRECTORY / "mixed-chart-matrixify.md",
        labels=(
            SeedLabel(
                name="validation:required",
                color="D93F0B",
                description="A committer should validate the issue",
            ),
        ),
    ),
}


@dataclass(frozen=True)
class SeedResult:
    created: bool
    issue_number: int
    issue_url: str


class GitHubClient:
    """Minimal asynchronous client for the GitHub Issues and Labels APIs."""

    def __init__(
        self,
        token: SecretStr,
        *,
        base_url: str = "https://api.github.com/",
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token.get_secret_value()}",
                "User-Agent": "cognition-fde-takehome-issue-seeder",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
            },
            timeout=timeout_seconds,
            transport=transport,
        )

    async def list_issues(self, repository: Repository) -> list[GitHubIssue]:
        issues: list[GitHubIssue] = []
        page = 1
        while True:
            response = await self._http.get(
                f"repos/{repository.full_name}/issues",
                params={"state": "all", "per_page": 100, "page": page},
            )
            response.raise_for_status()
            batch = TypeAdapter(list[GitHubIssue]).validate_json(
                response.content,
                strict=True,
            )
            issues.extend(batch)
            if len(batch) < 100:
                return issues
            page += 1

    async def ensure_label(
        self,
        repository: Repository,
        label: SeedLabel,
    ) -> GitHubLabel:
        response = await self._http.get(
            f"repos/{repository.full_name}/labels/{quote(label.name, safe='')}",
        )
        if response.status_code == httpx.codes.NOT_FOUND:
            request = CreateLabelRequest(
                name=label.name,
                color=label.color,
                description=label.description,
            )
            response = await self._http.post(
                f"repos/{repository.full_name}/labels",
                content=request.model_dump_json(),
                headers={"Content-Type": "application/json"},
            )
        response.raise_for_status()
        return GitHubLabel.model_validate_json(response.content, strict=True)

    async def create_issue(
        self,
        repository: Repository,
        request: CreateIssueRequest,
    ) -> GitHubIssue:
        response = await self._http.post(
            f"repos/{repository.full_name}/issues",
            content=request.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return GitHubIssue.model_validate_json(response.content, strict=True)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._http.aclose()


async def seed_issue(
    client: GitHubClient,
    repository: Repository,
    seed: SeedIssue,
) -> SeedResult:
    issues = await client.list_issues(repository)
    for issue in issues:
        if issue.body is not None and seed.marker in issue.body:
            return SeedResult(
                created=False,
                issue_number=issue.number,
                issue_url=issue.html_url,
            )

    for label in seed.labels:
        await client.ensure_label(repository, label)

    issue = await client.create_issue(
        repository,
        CreateIssueRequest(
            title=seed.title,
            body=seed.render_body(),
            labels=tuple(label.name for label in seed.labels),
        ),
    )
    return SeedResult(
        created=True,
        issue_number=issue.number,
        issue_url=issue.html_url,
    )


class CliNamespace(argparse.Namespace):
    repository: str
    issue: str
    apply: bool


@dataclass(frozen=True)
class CliArguments:
    repository: Repository
    issue: SeedIssue
    apply: bool


def parse_arguments(argv: Sequence[str] | None = None) -> CliArguments:
    parser = argparse.ArgumentParser(
        description="Seed a fork with a reproducible demonstration issue.",
    )
    parser.add_argument(
        "--repo",
        dest="repository",
        required=True,
        help="Target repository in OWNER/REPOSITORY format.",
    )
    parser.add_argument(
        "--issue",
        required=True,
        choices=tuple(SEED_CATALOG),
        help="Seed issue to create.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create the issue. Without this flag, only preview the payload.",
    )
    namespace = parser.parse_args(argv, namespace=CliNamespace())
    try:
        repository = Repository.parse(namespace.repository)
    except ValueError as error:
        parser.error(str(error))
    return CliArguments(
        repository=repository,
        issue=SEED_CATALOG[namespace.issue],
        apply=namespace.apply,
    )


def print_preview(arguments: CliArguments) -> None:
    labels = ", ".join(label.name for label in arguments.issue.labels)
    print(f"Target: {arguments.repository.full_name}")
    print(f"Seed: {arguments.issue.key}")
    print(f"Title: {arguments.issue.title}")
    print(f"Labels: {labels}")
    print("\nBody:\n")
    print(arguments.issue.render_body(), end="")


async def apply_seed(arguments: CliArguments) -> SeedResult:
    settings = GitHubSettings()
    async with GitHubClient(settings.github_token) as client:
        return await seed_issue(client, arguments.repository, arguments.issue)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    if not arguments.apply:
        print_preview(arguments)
        return 0

    result = asyncio.run(apply_seed(arguments))
    action = "Created" if result.created else "Already present"
    print(f"{action}: {result.issue_url} (issue #{result.issue_number})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
