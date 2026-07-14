import pytest
from httpx import ASGITransport, AsyncClient

from app import main


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_startup_and_health(monkeypatch: pytest.MonkeyPatch) -> None:
    initialized = False

    async def initialize_resources() -> None:
        nonlocal initialized
        initialized = True

    monkeypatch.setattr(main, "initialize_resources", initialize_resources)
    transport = ASGITransport(app=main.app)

    async with main.app.router.lifespan_context(main.app):
        assert initialized
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")
            dashboard = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert dashboard.status_code == 200
    assert "Scheduler running" in dashboard.text
