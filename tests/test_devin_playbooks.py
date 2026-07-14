import httpx
import pytest

from app.devin.client import DevinClient
from app.devin.models import (
    DevinPlaybook,
    DevinPlaybookPage,
    ManagedPlaybookDefinition,
)
from app.devin.playbooks import DevinPlaybooks, DuplicateManagedPlaybookError

# These simulations cover the third-party Devin API v3 network boundary and use
# the documented organization playbook schemas:
# List: https://docs.devin.ai/api-reference/v3/playbooks/organizations-playbooks
# Create: https://docs.devin.ai/api-reference/v3/playbooks/post-organizations-playbooks
# Update: https://docs.devin.ai/api-reference/v3/playbooks/put-organizations-playbooks-playbook-id


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _definition(
    body: str = "# Procedure\n\n1. Do the work.\n",
) -> ManagedPlaybookDefinition:
    return ManagedPlaybookDefinition(
        title="Managed playbook",
        body=body,
        macro="!managed-playbook",
    )


def _remote_playbook(
    definition: ManagedPlaybookDefinition,
    *,
    playbook_id: str = "playbook-managed",
) -> DevinPlaybook:
    return DevinPlaybook(
        access_type="org",
        body=definition.body,
        created_at=1,
        created_by="service-user",
        macro=definition.macro,
        org_id="org-test",
        playbook_id=playbook_id,
        title=definition.title,
        updated_at=1,
        updated_by="service-user",
        structured_output_schema=definition.structured_output_schema,
    )


def _page(*playbooks: DevinPlaybook) -> bytes:
    return (
        DevinPlaybookPage(
            items=list(playbooks),
            end_cursor=None,
            has_next_page=False,
            total=len(playbooks),
        )
        .model_dump_json()
        .encode()
    )


@pytest.mark.anyio
async def test_reconciliation_creates_a_missing_playbook() -> None:
    desired = _definition()
    methods: list[str] = []

    def handle_devin_request(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, content=_page())

        received = ManagedPlaybookDefinition.model_validate_json(request.content)
        return httpx.Response(
            200,
            content=_remote_playbook(received).model_dump_json().encode(),
        )

    transport = httpx.MockTransport(handle_devin_request)
    async with DevinClient(
        "cog_test",
        base_url="https://api.devin.test/v3/",
        transport=transport,
    ) as client:
        resolved = await DevinPlaybooks(client, "org-test").ensure_all((desired,))

    assert resolved == {"!managed-playbook": "playbook-managed"}
    assert methods == ["GET", "POST"]


@pytest.mark.anyio
async def test_reconciliation_leaves_a_matching_playbook_unchanged() -> None:
    desired = _definition()
    methods: list[str] = []

    def handle_devin_request(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(200, content=_page(_remote_playbook(desired)))

    transport = httpx.MockTransport(handle_devin_request)
    async with DevinClient(
        "cog_test",
        base_url="https://api.devin.test/v3/",
        transport=transport,
    ) as client:
        resolved = await DevinPlaybooks(client, "org-test").ensure_all((desired,))

    assert resolved == {"!managed-playbook": "playbook-managed"}
    assert methods == ["GET"]


@pytest.mark.anyio
async def test_reconciliation_updates_a_changed_playbook() -> None:
    desired = _definition()
    current = _remote_playbook(_definition(body="# Old procedure\n"))
    methods: list[str] = []

    def handle_devin_request(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, content=_page(current))

        received = ManagedPlaybookDefinition.model_validate_json(request.content)
        return httpx.Response(
            200,
            content=_remote_playbook(received).model_dump_json().encode(),
        )

    transport = httpx.MockTransport(handle_devin_request)
    async with DevinClient(
        "cog_test",
        base_url="https://api.devin.test/v3/",
        transport=transport,
    ) as client:
        resolved = await DevinPlaybooks(client, "org-test").ensure_all((desired,))

    assert resolved == {"!managed-playbook": "playbook-managed"}
    assert methods == ["GET", "PUT"]


@pytest.mark.anyio
async def test_reconciliation_rejects_duplicate_remote_macros() -> None:
    desired = _definition()

    def handle_devin_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=_page(
                _remote_playbook(desired, playbook_id="playbook-first"),
                _remote_playbook(desired, playbook_id="playbook-second"),
            ),
        )

    transport = httpx.MockTransport(handle_devin_request)
    async with DevinClient(
        "cog_test",
        base_url="https://api.devin.test/v3/",
        transport=transport,
    ) as client:
        with pytest.raises(DuplicateManagedPlaybookError):
            await DevinPlaybooks(client, "org-test").ensure_all((desired,))
