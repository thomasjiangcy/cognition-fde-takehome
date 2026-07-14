from pydantic import BaseModel, ConfigDict, Field


class GitHubLabel(BaseModel):
    """Label fields returned by GitHub's REST labels API."""

    model_config = ConfigDict(extra="ignore", strict=True)

    name: str = Field(min_length=1)
    color: str = Field(pattern=r"^[0-9A-Fa-f]{6}$")
    description: str | None = None


class GitHubLabelDefinition(BaseModel):
    """Fields required to create a GitHub label."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1)
    color: str = Field(pattern=r"^[0-9A-Fa-f]{6}$")
    description: str = Field(min_length=1)
