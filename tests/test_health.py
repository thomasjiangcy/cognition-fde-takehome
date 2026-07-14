import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_health() -> None:
    transport = ASGITransport(app=app)

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")
            dashboard = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert dashboard.status_code == 200
    assert "Scheduler running" in dashboard.text
