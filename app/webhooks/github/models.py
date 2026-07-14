from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, TypeAdapter

type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)


class GitHubUser(BaseModel):
    """GitHub user fields required for webhook routing and investigation."""

    model_config = ConfigDict(extra="ignore", strict=True)

    login: str = Field(min_length=1)


class GitHubIssueLabel(BaseModel):
    """GitHub issue label fields required for workflow classification."""

    model_config = ConfigDict(extra="ignore", strict=True)

    name: str = Field(min_length=1)


class GitHubIssue(BaseModel):
    """Issue fields consumed by the planned bug-investigation workflow."""

    model_config = ConfigDict(extra="ignore", strict=True)

    number: int = Field(ge=1)
    title: str = Field(min_length=1)
    body: str | None
    state: Literal["open", "closed"]
    html_url: str = Field(pattern=r"^https://github\.com/.+")
    user: GitHubUser
    labels: list[GitHubIssueLabel]


class GitHubRepository(BaseModel):
    """Repository identity included in GitHub webhook payloads."""

    model_config = ConfigDict(extra="ignore", strict=True)

    full_name: str = Field(pattern=r"^[^/\s]+/[^/\s]+$")


class GitHubIssuesPayload(BaseModel):
    """Validated subset of GitHub's issues webhook payload.

    GitHub documents many additional fields. They are deliberately ignored at
    this boundary because routing only needs the issue, repository, sender, and
    action, while retaining strict validation for every consumed field.
    """

    model_config = ConfigDict(extra="ignore", strict=True)

    action: str = Field(min_length=1)
    issue: GitHubIssue
    repository: GitHubRepository
    sender: GitHubUser


class GitHubPingPayload(BaseModel):
    """Validated subset of the ping sent when a webhook is created."""

    model_config = ConfigDict(extra="ignore", strict=True)

    zen: str
    hook_id: int
    repository: GitHubRepository


class GitHubUnknownPayload(RootModel[dict[str, JsonValue]]):
    """Strict JSON object retained for verified but unsupported event types."""

    model_config = ConfigDict(strict=True)


type GitHubPayload = GitHubIssuesPayload | GitHubPingPayload | GitHubUnknownPayload


class GitHubWebhookHeaders(BaseModel):
    """Required GitHub delivery headers consumed by the receiver."""

    model_config = ConfigDict(extra="forbid", strict=True)

    delivery_id: str = Field(min_length=1, max_length=128)
    event: str = Field(pattern=r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class GitHubDelivery:
    """Normalized, verified GitHub delivery ready for workflow routing."""

    delivery_id: str
    event: str
    action: str | None
    repository: str | None
    payload: GitHubPayload


_UNKNOWN_PAYLOAD_ADAPTER = TypeAdapter(GitHubUnknownPayload)


def parse_github_delivery(
    headers: GitHubWebhookHeaders,
    raw_body: bytes,
) -> GitHubDelivery:
    if headers.event == "issues":
        payload = GitHubIssuesPayload.model_validate_json(raw_body, strict=True)
        return GitHubDelivery(
            delivery_id=headers.delivery_id,
            event=headers.event,
            action=payload.action,
            repository=payload.repository.full_name,
            payload=payload,
        )

    if headers.event == "ping":
        payload = GitHubPingPayload.model_validate_json(raw_body, strict=True)
        return GitHubDelivery(
            delivery_id=headers.delivery_id,
            event=headers.event,
            action=None,
            repository=payload.repository.full_name,
            payload=payload,
        )

    payload = _UNKNOWN_PAYLOAD_ADAPTER.validate_json(raw_body, strict=True)
    return GitHubDelivery(
        delivery_id=headers.delivery_id,
        event=headers.event,
        action=None,
        repository=None,
        payload=payload,
    )
