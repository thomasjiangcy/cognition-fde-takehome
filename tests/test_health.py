import pytest
from httpx import ASGITransport, AsyncClient

from app import main


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_startup_and_health() -> None:
    transport = ASGITransport(app=main.app)

    async with main.app.router.lifespan_context(main.app):
        assert main.scheduler.running
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")
            dashboard = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert dashboard.status_code == 200
    assert "Scheduler running" in dashboard.text
