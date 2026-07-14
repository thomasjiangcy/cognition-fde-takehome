from collections.abc import Mapping
from types import TracebackType
from typing import Self

import httpx

type QueryValue = str | int


class DevinClient:
    """Authenticated asynchronous transport for Devin's v3 API."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.devin.ai/v3/",
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            timeout=timeout_seconds,
            transport=transport,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: str | None = None,
        query: Mapping[str, QueryValue] | None = None,
    ) -> bytes:
        headers = {"Content-Type": "application/json"} if json_body else None
        response = await self._http.request(
            method,
            path,
            content=json_body,
            headers=headers,
            params=query,
        )
        response.raise_for_status()
        return response.content

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()
