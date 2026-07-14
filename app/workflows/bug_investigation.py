from app.devin.models import DevinSessionCreateRequest
from app.devin.playbooks import PLAYBOOKS_DIR, ManagedPlaybookSpec
from app.devin.sessions import DevinSessions
from app.webhooks.github.models import GitHubDelivery, GitHubIssuesPayload
from app.workflows.dispatcher import WorkflowResult

BUG_INVESTIGATION_PLAYBOOK = ManagedPlaybookSpec(
    path=PLAYBOOKS_DIR / "bug-investigation.devin.md",
    title="Investigate Superset bug reports",
    macro="!investigate-superset-bug",
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
                structured_output_required=False,
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
