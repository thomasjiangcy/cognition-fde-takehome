import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import PostgresDsn

from app import main
from app.config import DatabaseSettings, DevinSettings
from app.devin.models import (
    DevinPlaybook,
    DevinPlaybookPage,
    ManagedPlaybookDefinition,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.database
async def test_startup_and_health(migrated_database_url: str) -> None:
    methods: list[str] = []

    # Simulates Devin's documented organization playbook list and create endpoints:
    # https://docs.devin.ai/api-reference/v3/playbooks/organizations-playbooks
    # https://docs.devin.ai/api-reference/v3/playbooks/post-organizations-playbooks
    def handle_devin_request(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "GET":
            page = DevinPlaybookPage(
                items=[],
                end_cursor=None,
                has_next_page=False,
                total=0,
            )
            return httpx.Response(200, content=page.model_dump_json().encode())

        received = ManagedPlaybookDefinition.model_validate_json(request.content)
        playbook_id = (
            "playbook-bug-investigation"
            if received.macro == "!investigate-superset-bug"
            else "playbook-bug-fix"
        )
        created = DevinPlaybook(
            access_type="org",
            body=received.body,
            created_at=1,
            created_by="service-user",
            macro=received.macro,
            org_id="org-test",
            playbook_id=playbook_id,
            title=received.title,
            updated_at=1,
            updated_by="service-user",
            structured_output_schema=received.structured_output_schema,
        )
        return httpx.Response(200, content=created.model_dump_json().encode())

    devin_transport = httpx.MockTransport(handle_devin_request)
    settings = DevinSettings(
        devin_org_id="org-test",
        devin_api_key="cog_test",
    )
    app_transport = ASGITransport(app=main.app)

    async with main.lifespan(
        main.app,
        database_settings=DatabaseSettings(
            database_url=PostgresDsn(migrated_database_url)
        ),
        devin_settings=settings,
        devin_transport=devin_transport,
    ):
        assert main.app.state.resources.playbook_ids == {
            "!investigate-superset-bug": "playbook-bug-investigation",
            "!fix-superset-bug": "playbook-bug-fix",
        }
        async with AsyncClient(
            transport=app_transport,
            base_url="http://test",
        ) as client:
            response = await client.get("/api/health")
            dashboard = await client.get("/")
            dashboard_data = await client.get("/api/dashboard")

    assert methods == ["GET", "POST", "POST"]
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert dashboard.status_code == 200
    assert "Devin automation dashboard" in dashboard.text
    assert "@knadh/oat@0.6.0" in dashboard.text
    assert 'id="live-mode"' in dashboard.text
    assert "refresh-dashboard" not in dashboard.text
    assert "Updated" not in dashboard.text
    assert "API documentation" not in dashboard.text
    assert dashboard_data.status_code == 200
    assert dashboard_data.json()["metrics"] == {
        "completed": 0,
        "in_progress": 0,
        "failed": 0,
    }
    assert dashboard_data.json()["runs"] == []
