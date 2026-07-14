from app.devin.models import DevinSessionCreateRequest, JsonObject
from app.devin.playbooks import PLAYBOOKS_DIR, ManagedPlaybookSpec
from app.devin.sessions import DevinSessions
from app.github.client import GitHubClient
from app.github.models import GitHubLabelDefinition
from app.webhooks.github.models import (
    GitHubDelivery,
    GitHubIssueLabel,
    GitHubIssuesPayload,
)
from app.workflows.dispatcher import WorkflowResult

# JSON Schema for the structured output that Devin must produce before ending
# the bug-fix session. Provisioning it makes the provide_structured_output tool
# available and forces Devin to call it with is_final=true.
BUG_FIX_STRUCTURED_OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "pr_url": {
            "type": "string",
            "format": "uri",
            "description": "URL of the opened pull request.",
        },
        "branch_name": {
            "type": "string",
            "description": "Name of the feature branch containing the fix.",
        },
        "summary": {
            "type": "string",
            "description": "One-sentence summary of the fix.",
        },
    },
    "required": ["pr_url", "branch_name", "summary"],
    "additionalProperties": False,
}

BUG_FIX_PLAYBOOK = ManagedPlaybookSpec(
    path=PLAYBOOKS_DIR / "bug-fix.devin.md",
    title="Fix a validated Superset bug and open a PR",
    macro="!fix-superset-bug",
    structured_output_schema=BUG_FIX_STRUCTURED_OUTPUT_SCHEMA,
)

DEVIN_ASSIGNED_LABEL = GitHubLabelDefinition(
    name="devin:assigned",
    color="0E8A16",
    description="A Devin session has been assigned to handle this issue",
)


class BugFixWorkflow:
    """Handle validated issues by opening a fix pull request."""

    name = "bug-fix"

    def __init__(
        self,
        sessions: DevinSessions,
        github_client: GitHubClient,
        playbook_id: str,
    ) -> None:
        self._sessions = sessions
        self._github_client = github_client
        self._playbook_id = playbook_id

    def matches(self, delivery: GitHubDelivery) -> bool:
        if delivery.event != "manual" or not isinstance(
            delivery.payload, GitHubIssuesPayload
        ):
            return False

        issue = delivery.payload.issue
        return self._is_validated_and_unassigned(issue.labels)

    @staticmethod
    def _is_validated_and_unassigned(
        labels: list[GitHubIssueLabel],
    ) -> bool:
        return any(
            label.name == "validation:validated" for label in labels
        ) and not any(label.name == "devin:assigned" for label in labels)

    async def run(self, delivery: GitHubDelivery) -> WorkflowResult:
        if not isinstance(delivery.payload, GitHubIssuesPayload):
            raise ValueError("Bug fix workflow requires a GitHub issues payload")

        payload = delivery.payload
        repository = delivery.repository
        if repository is None:
            raise ValueError("Bug fix workflow requires a repository")

        issue = payload.issue
        await self._github_client.add_label(
            repository, issue.number, DEVIN_ASSIGNED_LABEL.name
        )

        session = await self._sessions.create(
            DevinSessionCreateRequest(
                prompt=(
                    "Fix this validated bug and open a pull request using the "
                    "attached playbook.\n\n"
                    f"Repository: {repository}\n"
                    f"Issue: {issue.html_url}"
                ),
                playbook_id=self._playbook_id,
                repos=[repository],
                structured_output_schema=BUG_FIX_STRUCTURED_OUTPUT_SCHEMA,
                structured_output_required=True,
                tags=["github-automation", self.name],
                title=f"Fix {repository}#{issue.number}",
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
