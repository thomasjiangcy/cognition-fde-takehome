from enum import StrEnum
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)
type JsonObject = dict[str, JsonValue]


class ManagedPlaybookDefinition(BaseModel):
    """Desired state for a playbook managed by this application."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    macro: str = Field(pattern=r"^![A-Za-z0-9_-]+$")
    structured_output_schema: JsonObject | None = None


class DevinPlaybook(BaseModel):
    """Validated v3 playbook representation returned by Devin."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    access_type: Literal["enterprise", "org"]
    body: str
    created_at: int
    created_by: str
    macro: str | None
    org_id: str | None
    playbook_id: str = Field(pattern=r"^playbook-.+$")
    title: str
    updated_at: int
    updated_by: str
    structured_output_schema: JsonObject | None = None


class DevinPlaybookPage(BaseModel):
    """Validated page returned by the v3 list-playbooks endpoint."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    items: list[DevinPlaybook]
    end_cursor: str | None
    has_next_page: bool
    total: int | None


class DevinSessionStatus(StrEnum):
    NEW = "new"
    CLAIMED = "claimed"
    RUNNING = "running"
    EXIT = "exit"
    ERROR = "error"
    SUSPENDED = "suspended"
    RESUMING = "resuming"


class DevinSessionStatusDetail(StrEnum):
    WORKING = "working"
    WAITING_FOR_USER = "waiting_for_user"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    FINISHED = "finished"
    INACTIVITY = "inactivity"
    USER_REQUEST = "user_request"
    USAGE_LIMIT_EXCEEDED = "usage_limit_exceeded"
    OUT_OF_CREDITS = "out_of_credits"
    OUT_OF_QUOTA = "out_of_quota"
    NO_QUOTA_ALLOCATION = "no_quota_allocation"
    PAYMENT_DECLINED = "payment_declined"
    ORG_USAGE_LIMIT_EXCEEDED = "org_usage_limit_exceeded"
    TOTAL_SESSION_LIMIT_EXCEEDED = "total_session_limit_exceeded"
    ERROR = "error"


class DevinSessionCreateRequest(BaseModel):
    """Validated v3 request used to start a workflow session."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    prompt: str = Field(min_length=1)
    playbook_id: str = Field(pattern=r"^playbook-.+$")
    repos: list[str] = Field(min_length=1)
    structured_output_required: Literal[False] = False
    tags: list[str] = Field(min_length=1)
    title: str = Field(min_length=1)


class DevinSession(BaseModel):
    """Validated v3 session representation returned by Devin."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    session_id: str = Field(pattern=r"^devin-.+$")
    url: AnyHttpUrl
    status: DevinSessionStatus
    status_detail: DevinSessionStatusDetail | None = None
    tags: list[str]
    org_id: str = Field(pattern=r"^org-.+$")
    created_at: int
    updated_at: int
    acus_consumed: float
