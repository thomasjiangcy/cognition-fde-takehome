import httpx
import pytest

from app.devin.client import DevinClient
from app.devin.models import (
    DevinPlaybook,
    DevinPlaybookPage,
    ManagedPlaybookDefinition,
)
from app.devin.playbooks import DevinPlaybooks, DuplicateManagedPlaybookError
from app.initialization import MANAGED_PLAYBOOKS
from app.workflows.bug_fix import BUG_FIX_PLAYBOOK
from app.workflows.bug_investigation import BUG_INVESTIGATION_PLAYBOOK

# These simulations cover the third-party Devin API v3 network boundary and use
# the documented organization playbook schemas:
# List: https://docs.devin.ai/api-reference/v3/playbooks/organizations-playbooks
# Create: https://docs.devin.ai/api-reference/v3/playbooks/post-organizations-playbooks
# Update: https://docs.devin.ai/api-reference/v3/playbooks/put-organizations-playbooks-playbook-id


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_bug_investigation_playbook_is_registered_with_structured_output() -> None:
    assert MANAGED_PLAYBOOKS == (BUG_INVESTIGATION_PLAYBOOK, BUG_FIX_PLAYBOOK)

    definition = BUG_INVESTIGATION_PLAYBOOK.load()

    assert definition.title == "Investigate Superset bug reports"
    assert definition.macro == "!investigate-superset-bug"
    assert definition.structured_output_schema is not None
    assert definition.structured_output_schema["type"] == "object"
    properties = definition.structured_output_schema["properties"]
    assert isinstance(properties, dict)
    assert "outcome" in properties
    assert "Post the final report as a comment" in definition.body
    assert "record a short video" in definition.body
    assert "Do not implement a fix" in definition.body
    assert "provide_structured_output" in definition.body


def test_bug_fix_playbook_is_registered_with_structured_output() -> None:
    definition = BUG_FIX_PLAYBOOK.load()

    assert definition.title == "Fix a validated Superset bug and open a PR"
    assert definition.macro == "!fix-superset-bug"
    assert definition.structured_output_schema is not None
    assert definition.structured_output_schema["type"] == "object"
    properties = definition.structured_output_schema["properties"]
    assert isinstance(properties, dict)
    assert "pr_url" in properties
    assert "branch_name" in properties
    assert "open a pull request" in definition.body
    assert "provide_structured_output" in definition.body


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
async def test_reconciliation_upserts_a_matching_playbook() -> None:
    desired = _definition()
    current = _remote_playbook(desired)
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


@pytest.mark.anyio
async def test_reconciliation_rejects_duplicate_desired_macros_before_request() -> None:
    methods: list[str] = []

    def handle_devin_request(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(200, content=_page())

    desired = _definition()
    transport = httpx.MockTransport(handle_devin_request)
    async with DevinClient(
        "cog_test",
        base_url="https://api.devin.test/v3/",
        transport=transport,
    ) as client:
        with pytest.raises(DuplicateManagedPlaybookError):
            await DevinPlaybooks(client, "org-test").ensure_all((desired, desired))

    assert methods == []
