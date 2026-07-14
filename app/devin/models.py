from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
