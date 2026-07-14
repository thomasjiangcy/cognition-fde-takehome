from pydantic import AnyHttpUrl, Field, SecretStr
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


class ObservabilitySettings(BaseSettings):
    """Optional OTLP destination parsed from the process environment."""

    model_config = SettingsConfigDict(extra="ignore", strict=True)

    otel_exporter_otlp_endpoint: AnyHttpUrl | None = None


def load_observability_settings() -> ObservabilitySettings:
    return ObservabilitySettings()


class GitHubWebhookSettings(BaseSettings):
    """Optional webhook secret read from the container process environment."""

    model_config = SettingsConfigDict(extra="ignore", strict=True)

    github_webhook_secret: SecretStr | None = None


def load_github_webhook_settings() -> GitHubWebhookSettings:
    return GitHubWebhookSettings()
