import logging
from dataclasses import dataclass

import httpx

from app.config import DevinSettings, load_devin_settings
from app.devin.client import DevinClient
from app.devin.playbooks import DevinPlaybooks, ManagedPlaybookSpec
from app.workflows.initial_workflow import BUG_INVESTIGATION_PLAYBOOK

logger = logging.getLogger(__name__)

MANAGED_PLAYBOOKS: tuple[ManagedPlaybookSpec, ...] = (BUG_INVESTIGATION_PLAYBOOK,)


@dataclass(frozen=True, slots=True)
class InitializedResources:
    playbook_ids: dict[str, str]


async def initialize_resources(
    *,
    managed_playbooks: tuple[ManagedPlaybookSpec, ...] = MANAGED_PLAYBOOKS,
    settings: DevinSettings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> InitializedResources:
    """Idempotently reconcile external resources required by the application."""
    if not managed_playbooks:
        logger.info("No managed Devin playbooks are configured")
        return InitializedResources(playbook_ids={})

    resolved_settings = settings if settings is not None else load_devin_settings()
    desired = tuple(spec.load() for spec in managed_playbooks)

    async with DevinClient(
        api_key=resolved_settings.devin_api_key,
        transport=transport,
    ) as client:
        playbooks = DevinPlaybooks(client, resolved_settings.devin_org_id)
        playbook_ids = await playbooks.ensure_all(desired)

    logger.info("Reconciled %d managed Devin playbooks", len(playbook_ids))
    return InitializedResources(playbook_ids=playbook_ids)
