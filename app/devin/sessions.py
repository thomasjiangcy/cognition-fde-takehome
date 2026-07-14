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

    async def get(self, session_id: str) -> DevinSession:
        content = await self._client.request("GET", f"{self._path}/{session_id}")
        return DevinSession.model_validate_json(content)

    async def terminate(
        self, session_id: str, *, archive: bool = False
    ) -> DevinSession:
        """Terminate a running Devin session so it stops consuming resources.

        Devin returns the session in the response; the session's ``status`` may
        still be ``running`` while ``is_archived`` is set to ``True``.
        """
        content = await self._client.request(
            "DELETE",
            f"{self._path}/{session_id}",
            query={"archive": "true" if archive else "false"},
        )
        return DevinSession.model_validate_json(content)
