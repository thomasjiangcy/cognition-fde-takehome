from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import uuid4

import pytest

from app.config import DevinSettings, load_devin_settings
from app.devin.client import DevinClient
from app.devin.models import DevinPlaybook
from app.devin.playbooks import DevinPlaybooks, ManagedPlaybookSpec
from app.initialization import initialize_resources
from app.workflows.bug_investigation import BUG_INVESTIGATION_PLAYBOOK

pytestmark = [pytest.mark.anyio, pytest.mark.live]


@dataclass(frozen=True, slots=True)
class LivePlaybookCase:
    settings: DevinSettings
    spec: ManagedPlaybookSpec


@pytest.fixture
async def live_playbook_case() -> AsyncIterator[LivePlaybookCase]:
    settings = load_devin_settings()
    identifier = uuid4().hex
    spec = ManagedPlaybookSpec(
        path=BUG_INVESTIGATION_PLAYBOOK.path,
        title=f"Cognition FDE live playbook {identifier}",
        macro=f"!cognition-fde-live-{identifier}",
    )
    case = LivePlaybookCase(settings=settings, spec=spec)

    try:
        yield case
    finally:
        async with DevinClient(api_key=settings.devin_api_key) as client:
            playbooks = DevinPlaybooks(client, settings.devin_org_id)
            matches = tuple(
                playbook
                for playbook in await playbooks.list_all()
                if playbook.macro == spec.macro
            )
            for playbook in matches:
                # Devin API v3, Delete an org-level playbook:
                # https://docs.devin.ai/api-reference/v3/playbooks/delete-organizations-playbooks-playbook-id
                content = await client.request(
                    "DELETE",
                    f"organizations/{settings.devin_org_id}/playbooks/{playbook.playbook_id}",
                )
                deleted = DevinPlaybook.model_validate_json(content)
                assert deleted.playbook_id == playbook.playbook_id


async def test_initialization_creates_missing_playbook(
    live_playbook_case: LivePlaybookCase,
) -> None:
    initialized = await initialize_resources(
        managed_playbooks=(live_playbook_case.spec,),
        settings=live_playbook_case.settings,
    )

    playbook_id = initialized.playbook_ids[live_playbook_case.spec.macro]
    assert playbook_id.startswith("playbook-")


async def test_initialization_reuses_existing_matching_playbook(
    live_playbook_case: LivePlaybookCase,
) -> None:
    desired = live_playbook_case.spec.load()
    async with DevinClient(api_key=live_playbook_case.settings.devin_api_key) as client:
        playbooks = DevinPlaybooks(client, live_playbook_case.settings.devin_org_id)
        existing = await playbooks.create(desired)

    initialized = await initialize_resources(
        managed_playbooks=(live_playbook_case.spec,),
        settings=live_playbook_case.settings,
    )

    assert initialized.playbook_ids[live_playbook_case.spec.macro] == (
        existing.playbook_id
    )
