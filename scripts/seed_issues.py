from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Protocol, Self
from urllib.parse import quote

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    TypeAdapter,
    ValidationError,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

GITHUB_API_VERSION = "2022-11-28"
SEEDS_DIRECTORY = Path(__file__).with_name("seeds")


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
class SeedLabel:
    name: str
    color: str
    description: str


@dataclass(frozen=True)
class SeedIssue:
    key: str
    title: str
    body_path: Path
    labels: tuple[SeedLabel, ...]
    repo_labels: tuple[SeedLabel, ...] = ()

    def render_body(self) -> str:
        return self.body_path.read_text(encoding="utf-8").removesuffix("\n")


SEED_CATALOG: dict[str, SeedIssue] = {
    "mixed-chart-matrixify": SeedIssue(
        key="apache-superset-39007",
        title="6.1.0rc1 - matrixify not applying to query B in Mixed Chart",
        body_path=SEEDS_DIRECTORY / "mixed-chart-matrixify.md",
        labels=(
            SeedLabel(
                name="validation:required",
                color="D93F0B",
                description="A committer should validate the issue",
            ),
        ),
        repo_labels=(
            SeedLabel(
                name="validation:validated",
                color="4F9031",
                description="A committer has validated / submitted the issue or it was reported by multiple users",
            ),
            SeedLabel(
                name="#bug:cant-reproduce",
                color="ededed",
                description="Bugs that cannot be reproduced",
            ),
        ),
    ),
}


@dataclass(frozen=True)
class SeedResult:
    created: bool
    issue_number: int
    issue_url: str


class GitHubAuthenticationError(RuntimeError):
    """Raised when neither gh nor token authentication is available."""


class GitHubIssueClient(Protocol):
    async def list_issues(self, repository: Repository) -> list[GitHubIssue]: ...

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

    async def list_issues(self, repository: Repository) -> list[GitHubIssue]:
        issues: list[GitHubIssue] = []
        page = 1
        while True:
            response = await self._http.get(
                f"repos/{repository.full_name}/issues",
                params={"state": "open", "per_page": 100, "page": page},
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


class GitHubCliClient:
    """GitHub operations executed through an authenticated gh CLI."""

    def __init__(self, executable: str) -> None:
        self._executable = executable

    async def list_issues(self, repository: Repository) -> list[GitHubIssue]:
        content = await self._api(
            "GET",
            f"repos/{repository.full_name}/issues",
            fields=("state=open", "per_page=100"),
            paginate=True,
        )
        pages = TypeAdapter(list[list[GitHubIssue]]).validate_json(
            self._require_content(content),
            strict=True,
        )
        return [issue for page in pages for issue in page]

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
        paginate: bool = False,
        check: bool = True,
    ) -> bytes | None:
        command = [self._executable, "api", "--method", method]
        if paginate:
            command.extend(("--paginate", "--slurp"))
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
    issues = await client.list_issues(repository)
    seed_body = seed.render_body()
    for issue in issues:
        if issue.title == seed.title and issue.body == seed_body:
            return SeedResult(
                created=False,
                issue_number=issue.number,
                issue_url=issue.html_url,
            )

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
        created=True,
        issue_number=issue.number,
        issue_url=issue.html_url,
    )


class CliNamespace(argparse.Namespace):
    repository: str | None
    issue: str
    dry_run: bool


@dataclass(frozen=True)
class CliArguments:
    repository: Repository
    issue: SeedIssue
    dry_run: bool


def parse_arguments(argv: Sequence[str] | None = None) -> CliArguments:
    parser = argparse.ArgumentParser(
        description="Seed a fork with a reproducible demonstration issue.",
    )
    parser.add_argument(
        "issue",
        choices=tuple(SEED_CATALOG),
        help="Seed issue to create.",
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
    repository_value = namespace.repository
    if repository_value is None:
        try:
            repository_value = SeedTargetSettings().github_repository
        except ValidationError:
            parser.error(
                "--repo OWNER/REPOSITORY is required when GITHUB_REPOSITORY is not set"
            )
    try:
        repository = Repository.parse(repository_value)
    except ValueError as error:
        parser.error(str(error))
    return CliArguments(
        repository=repository,
        issue=SEED_CATALOG[namespace.issue],
        dry_run=namespace.dry_run,
    )


def print_preview(arguments: CliArguments) -> None:
    labels = ", ".join(label.name for label in arguments.issue.labels)
    print(f"Target: {arguments.repository.full_name}")
    print(f"Seed: {arguments.issue.key}")
    print(f"Title: {arguments.issue.title}")
    print(f"Labels: {labels}")
    print("\nBody:\n")
    print(arguments.issue.render_body())


async def apply_seed(arguments: CliArguments) -> SeedResult:
    gh_executable = await authenticated_gh()
    if gh_executable is not None:
        return await seed_issue(
            GitHubCliClient(gh_executable),
            arguments.repository,
            arguments.issue,
        )

    token = GitHubSettings().github_token
    if token is None:
        raise GitHubAuthenticationError(
            "GitHub authentication is required: run `gh auth login` or set "
            "GITHUB_TOKEN to a token with Issues write permission"
        )
    async with GitHubClient(token) as client:
        return await seed_issue(client, arguments.repository, arguments.issue)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    if arguments.dry_run:
        print_preview(arguments)
        return 0

    try:
        result = asyncio.run(apply_seed(arguments))
    except GitHubAuthenticationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    action = "Created" if result.created else "Already present"
    print(f"{action}: {result.issue_url} (issue #{result.issue_number})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
