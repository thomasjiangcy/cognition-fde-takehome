from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol, Self
from urllib.parse import quote

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.seeds import SEED_CATALOG, SeedIssue, SeedLabel

GITHUB_API_VERSION = "2022-11-28"
DEFAULT_REPOSITORY = "thomasjiangcy/superset"


class GitHubSettings(BaseSettings):
    """Authentication used only when applying a seed to GitHub."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        strict=True,
    )

    github_token: SecretStr | None = Field(default=None, min_length=1)


class SeedTargetSettings(BaseSettings):
    """Default GitHub repository targeted by the local demo seeder."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        strict=True,
    )

    github_repository: str = Field(min_length=3)


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
class SeedResult:
    issue_number: int
    issue_url: str


class GitHubAuthenticationError(RuntimeError):
    """Raised when neither gh nor token authentication is available."""


class GitHubIssueClient(Protocol):
    async def ensure_label(
        self,
        repository: Repository,
        label: SeedLabel,
    ) -> GitHubLabel: ...

    async def create_issue(
        self,
        repository: Repository,
        request: CreateIssueRequest,
    ) -> GitHubIssue: ...


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


class GitHubCliClient:
    """GitHub operations executed through an authenticated gh CLI."""

    def __init__(self, executable: str) -> None:
        self._executable = executable

    async def ensure_label(
        self,
        repository: Repository,
        label: SeedLabel,
    ) -> GitHubLabel:
        path = f"repos/{repository.full_name}/labels/{quote(label.name, safe='')}"
        content = await self._api("GET", path, check=False)
        if not content:
            request = CreateLabelRequest(
                name=label.name,
                color=label.color,
                description=label.description,
            )
            content = await self._api(
                "POST",
                f"repos/{repository.full_name}/labels",
                request_body=request.model_dump_json().encode(),
            )
        return GitHubLabel.model_validate_json(
            self._require_content(content),
            strict=True,
        )

    async def create_issue(
        self,
        repository: Repository,
        request: CreateIssueRequest,
    ) -> GitHubIssue:
        content = await self._api(
            "POST",
            f"repos/{repository.full_name}/issues",
            request_body=request.model_dump_json().encode(),
        )
        return GitHubIssue.model_validate_json(
            self._require_content(content),
            strict=True,
        )

    @staticmethod
    def _require_content(content: bytes | None) -> bytes:
        if content is None:
            raise GitHubAuthenticationError("gh returned no GitHub API response")
        return content

    async def _api(
        self,
        method: str,
        path: str,
        *,
        fields: tuple[str, ...] = (),
        request_body: bytes | None = None,
        check: bool = True,
    ) -> bytes | None:
        command = [self._executable, "api", "--method", method]
        command.append(path)
        for field in fields:
            command.extend(("--field", field))
        if request_body is not None:
            command.extend(("--input", "-"))

        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=(asyncio.subprocess.PIPE if request_body is not None else None),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await process.communicate(request_body)
        if process.returncode == 0:
            return stdout
        if not check:
            return None
        raise GitHubAuthenticationError(
            "gh could not access the target repository; run `gh auth status` and "
            "confirm the active account has Issues write permission"
        )


async def authenticated_gh() -> str | None:
    executable = shutil.which("gh")
    if executable is None:
        return None
    process = await asyncio.create_subprocess_exec(
        executable,
        "auth",
        "status",
        "--hostname",
        "github.com",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    if await process.wait() != 0:
        return None
    return executable


async def seed_issue(
    client: GitHubIssueClient,
    repository: Repository,
    seed: SeedIssue,
) -> SeedResult:
    seed_body = seed.render_body()

    for label in seed.labels + seed.repo_labels:
        await client.ensure_label(repository, label)

    issue = await client.create_issue(
        repository,
        CreateIssueRequest(
            title=seed.title,
            body=seed_body,
            labels=tuple(label.name for label in seed.labels),
        ),
    )
    return SeedResult(
        issue_number=issue.number,
        issue_url=issue.html_url,
    )


class CliNamespace(argparse.Namespace):
    repository: str | None
    issue: str | None
    all: bool
    dry_run: bool


@dataclass(frozen=True)
class CliArguments:
    repository: Repository
    issues: tuple[SeedIssue, ...]
    dry_run: bool


def parse_arguments(argv: Sequence[str] | None = None) -> CliArguments:
    parser = argparse.ArgumentParser(
        description="Seed a fork with a reproducible demonstration issue.",
    )
    parser.add_argument(
        "issue",
        nargs="?",
        default=None,
        choices=tuple(SEED_CATALOG) + ("all",),
        help="Seed issue to create, or 'all' to seed every issue.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Seed every configured issue.",
    )
    parser.add_argument(
        "--repo",
        dest="repository",
        help="Override GITHUB_REPOSITORY with an OWNER/REPOSITORY target.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the payload without contacting GitHub.",
    )
    namespace = parser.parse_args(argv, namespace=CliNamespace())
    if namespace.issue == "all" or namespace.all:
        issues = tuple(SEED_CATALOG.values())
    elif namespace.issue is None:
        parser.error("issue is required unless --all is used")
    else:
        issues = (SEED_CATALOG[namespace.issue],)
    repository_value = namespace.repository
    if repository_value is None:
        try:
            repository_value = SeedTargetSettings().github_repository
        except ValidationError:
            repository_value = DEFAULT_REPOSITORY
    try:
        repository = Repository.parse(repository_value)
    except ValueError as error:
        parser.error(str(error))
    return CliArguments(
        repository=repository,
        issues=issues,
        dry_run=namespace.dry_run,
    )


def print_preview(repository: Repository, issue: SeedIssue) -> None:
    labels = ", ".join(label.name for label in issue.labels)
    print(f"Target: {repository.full_name}")
    print(f"Seed: {issue.key}")
    print(f"Title: {issue.title}")
    print(f"Labels: {labels}")
    print("\nBody:\n")
    print(issue.render_body())


async def apply_seeds(
    repository: Repository,
    issues: Sequence[SeedIssue],
) -> list[SeedResult]:
    gh_executable = await authenticated_gh()
    if gh_executable is not None:
        client = GitHubCliClient(gh_executable)
        return [await seed_issue(client, repository, issue) for issue in issues]

    token = GitHubSettings().github_token
    if token is None:
        raise GitHubAuthenticationError(
            "GitHub authentication is required: run `gh auth login` or set "
            "GITHUB_TOKEN to a token with Issues write permission"
        )
    async with GitHubClient(token) as client:
        return [await seed_issue(client, repository, issue) for issue in issues]


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    if arguments.dry_run:
        for issue in arguments.issues:
            print_preview(arguments.repository, issue)
            print("---")
        return 0

    try:
        results = asyncio.run(apply_seeds(arguments.repository, arguments.issues))
    except GitHubAuthenticationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for result in results:
        print(f"Created: {result.issue_url} (issue #{result.issue_number})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
