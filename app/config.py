from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DevinSettings(BaseSettings):
    """Strict Devin API settings loaded from the environment or local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        strict=True,
    )

    devin_org_id: str = Field(pattern=r"^org-.+$")
    devin_api_key: str = Field(pattern=r"^cog_.+$", repr=False)


def load_devin_settings() -> DevinSettings:
    return DevinSettings()
