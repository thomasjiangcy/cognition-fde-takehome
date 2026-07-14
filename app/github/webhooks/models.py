from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GitHubDelivery:
    """Normalized GitHub delivery passed to workflow routing."""

    delivery_id: str
    event: str
    action: str | None
    repository: str | None
    payload: dict[str, Any]
