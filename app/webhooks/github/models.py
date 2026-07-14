from dataclasses import dataclass

type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)


@dataclass(frozen=True)
class GitHubDelivery:
    """Normalized GitHub delivery passed to workflow routing."""

    delivery_id: str
    event: str
    action: str | None
    repository: str | None
    payload: dict[str, JsonValue]
