from app.devin.client import DevinClient
from app.devin.models import DevinSession, DevinSessionCreateRequest


class DevinSessions:
    """Create and retrieve workflow sessions through Devin's v3 API."""

    def __init__(self, client: DevinClient, org_id: str) -> None:
        self._client = client
        self._path = f"organizations/{org_id}/sessions"

    async def create(self, request: DevinSessionCreateRequest) -> DevinSession:
        content = await self._client.request(
            "POST",
            self._path,
            json_body=request.model_dump_json(),
        )
        return DevinSession.model_validate_json(content)
