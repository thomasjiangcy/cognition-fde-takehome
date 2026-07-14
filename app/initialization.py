import logging
from dataclasses import dataclass

from app.config import load_devin_settings
from app.devin.client import DevinClient
from app.devin.playbooks import MANAGED_PLAYBOOKS, DevinPlaybooks

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class InitializedResources:
    playbook_ids: dict[str, str]


async def initialize_resources() -> InitializedResources:
    """Idempotently reconcile external resources required by the application."""
    if not MANAGED_PLAYBOOKS:
        logger.info("No managed Devin playbooks are configured")
        return InitializedResources(playbook_ids={})

    settings = load_devin_settings()
    desired = tuple(spec.load() for spec in MANAGED_PLAYBOOKS)

    async with DevinClient(api_key=settings.devin_api_key) as client:
        playbooks = DevinPlaybooks(client, settings.devin_org_id)
        playbook_ids = await playbooks.ensure_all(desired)

    logger.info("Reconciled %d managed Devin playbooks", len(playbook_ids))
    return InitializedResources(playbook_ids=playbook_ids)
