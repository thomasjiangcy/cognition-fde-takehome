from dataclasses import dataclass
from pathlib import Path

import httpx

from app.devin.client import DevinClient, QueryValue
from app.devin.models import (
    DevinPlaybook,
    DevinPlaybookPage,
    JsonObject,
    ManagedPlaybookDefinition,
)

PLAYBOOKS_DIR = Path(__file__).resolve().parents[2] / "playbooks"


@dataclass(frozen=True, slots=True)
class ManagedPlaybookSpec:
    """Local file and API metadata for one application-managed playbook."""

    path: Path
    title: str
    macro: str
    structured_output_schema: JsonObject | None = None

    def load(self) -> ManagedPlaybookDefinition:
        return ManagedPlaybookDefinition(
            title=self.title,
            body=self.path.read_text(encoding="utf-8"),
            macro=self.macro,
            structured_output_schema=self.structured_output_schema,
        )


class DuplicateManagedPlaybookError(RuntimeError):
    """Raised when a managed macro does not identify exactly one playbook."""


class InvalidPlaybookPaginationError(RuntimeError):
    """Raised when Devin reports another page without returning a cursor."""


class DevinPlaybooks:
    """Reconcile application-managed playbooks through Devin's v3 API."""

    def __init__(self, client: DevinClient, org_id: str) -> None:
        self._client = client
        self._path = f"organizations/{org_id}/playbooks"

    async def list_all(self) -> tuple[DevinPlaybook, ...]:
        playbooks: list[DevinPlaybook] = []
        cursor: str | None = None

        while True:
            query: dict[str, QueryValue] = {"first": 200}
            if cursor is not None:
                query["after"] = cursor

            content = await self._client.request("GET", self._path, query=query)
            page = DevinPlaybookPage.model_validate_json(content)
            playbooks.extend(page.items)

            if not page.has_next_page:
                return tuple(playbooks)
            if page.end_cursor is None:
                raise InvalidPlaybookPaginationError
            cursor = page.end_cursor

    async def create(self, desired: ManagedPlaybookDefinition) -> DevinPlaybook:
        content = await self._client.request(
            "POST",
            self._path,
            json_body=desired.model_dump_json(),
        )
        return DevinPlaybook.model_validate_json(content)

    async def update(
        self,
        playbook_id: str,
        desired: ManagedPlaybookDefinition,
    ) -> DevinPlaybook:
        content = await self._client.request(
            "PUT",
            f"{self._path}/{playbook_id}",
            json_body=desired.model_dump_json(),
        )
        return DevinPlaybook.model_validate_json(content)

    async def ensure_all(
        self,
        desired_playbooks: tuple[ManagedPlaybookDefinition, ...],
    ) -> dict[str, str]:
        desired_macros: set[str] = set()
        for desired in desired_playbooks:
            if desired.macro in desired_macros:
                raise DuplicateManagedPlaybookError(desired.macro)
            desired_macros.add(desired.macro)

        existing = list(await self.list_all())
        resolved: dict[str, str] = {}

        for desired in desired_playbooks:
            ensured = await self._ensure_one(desired, existing)
            resolved[desired.macro] = ensured.playbook_id
            existing = [
                playbook
                for playbook in existing
                if playbook.playbook_id != ensured.playbook_id
            ]
            existing.append(ensured)

        return resolved

    async def _ensure_one(
        self,
        desired: ManagedPlaybookDefinition,
        existing: list[DevinPlaybook],
    ) -> DevinPlaybook:
        matches = self._matching_macro(desired.macro, existing)
        if len(matches) > 1:
            raise DuplicateManagedPlaybookError(desired.macro)

        if not matches:
            try:
                return await self.create(desired)
            except httpx.HTTPStatusError as error:
                if error.response.status_code not in {409, 422}:
                    raise

                refreshed = list(await self.list_all())
                matches = self._matching_macro(desired.macro, refreshed)
                if not matches:
                    raise
                if len(matches) > 1:
                    raise DuplicateManagedPlaybookError(desired.macro) from error

        current = matches[0]
        return await self.update(current.playbook_id, desired)

    @staticmethod
    def _matching_macro(
        macro: str,
        playbooks: list[DevinPlaybook],
    ) -> list[DevinPlaybook]:
        return [playbook for playbook in playbooks if playbook.macro == macro]
