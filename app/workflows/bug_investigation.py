from app.devin.models import DevinSessionCreateRequest, JsonObject
from app.devin.playbooks import PLAYBOOKS_DIR, ManagedPlaybookSpec
from app.devin.sessions import DevinSessions
from app.webhooks.github.models import GitHubDelivery, GitHubIssuesPayload
from app.workflows.dispatcher import WorkflowResult

# JSON Schema (Draft 7) for the structured output that Devin must produce before
# ending the session.  Provisioning this schema on the session create request
# makes the ``provide_structured_output`` tool available; setting
# ``structured_output_required=True`` forces Devin to call it with
# ``is_final=true``, giving the session a deterministic termination path.
# https://docs.devin.ai/api-reference/v1/structured-output
BUG_INVESTIGATION_STRUCTURED_OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "outcome": {
            "type": "string",
            "enum": ["confirmed", "not_reproduced", "blocked", "invalid"],
            "description": "Investigation outcome matching the report's Outcome field.",
        },
        "summary": {
            "type": "string",
            "description": "One-sentence conclusion and impact.",
        },
        "issue_comment_url": {
            "type": "string",
            "format": "uri",
            "description": "URL of the investigation comment posted on the GitHub issue.",
        },
        "root_cause": {
            "type": ["string", "null"],
            "description": "Evidence-backed root cause, or null when not identified.",
        },
    },
    "required": ["outcome", "summary", "issue_comment_url", "root_cause"],
    "additionalProperties": False,
}

BUG_INVESTIGATION_PLAYBOOK = ManagedPlaybookSpec(
    path=PLAYBOOKS_DIR / "bug-investigation.devin.md",
    title="Investigate Superset bug reports",
    macro="!investigate-superset-bug",
    structured_output_schema=BUG_INVESTIGATION_STRUCTURED_OUTPUT_SCHEMA,
)


class BugInvestigationWorkflow:
    """Investigate newly opened issues that use Superset's bug template."""

    name = "bug-investigation"

    def __init__(self, sessions: DevinSessions, playbook_id: str) -> None:
        self._sessions = sessions
        self._playbook_id = playbook_id

    def matches(self, delivery: GitHubDelivery) -> bool:
        if (
            delivery.event != "issues"
            or delivery.action != "opened"
            or not isinstance(delivery.payload, GitHubIssuesPayload)
        ):
            return False

        body = delivery.payload.issue.body
        return body is not None and "### Bug description" in body

    async def run(self, delivery: GitHubDelivery) -> WorkflowResult:
        if not isinstance(delivery.payload, GitHubIssuesPayload):
            raise ValueError("Bug investigation requires a GitHub issues payload")

        payload = delivery.payload
        session = await self._sessions.create(
            DevinSessionCreateRequest(
                prompt=(
                    "Investigate this bug report using the attached playbook.\n\n"
                    f"Repository: {payload.repository.full_name}\n"
                    f"Issue: {payload.issue.html_url}"
                ),
                playbook_id=self._playbook_id,
                repos=[payload.repository.full_name],
                structured_output_schema=BUG_INVESTIGATION_STRUCTURED_OUTPUT_SCHEMA,
                structured_output_required=True,
                tags=["github-automation", self.name],
                title=f"Investigate {payload.repository.full_name}#{payload.issue.number}",
            )
        )
        return WorkflowResult(
            devin_session_id=session.session_id,
            devin_status=session.status.value,
            devin_status_detail=(
                session.status_detail.value
                if session.status_detail is not None
                else None
            ),
        )
