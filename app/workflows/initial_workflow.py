from app.devin.playbooks import PLAYBOOKS_DIR, ManagedPlaybookSpec
from app.webhooks.github.models import GitHubDelivery, GitHubIssuesPayload

BUG_INVESTIGATION_PLAYBOOK = ManagedPlaybookSpec(
    path=PLAYBOOKS_DIR / "bug-investigation.devin.md",
    title="Investigate Superset bug reports",
    macro="!investigate-superset-bug",
)


class BugInvestigationWorkflow:
    """Investigate newly opened issues that use Superset's bug template."""

    name = "bug-investigation"

    def matches(self, delivery: GitHubDelivery) -> bool:
        if (
            delivery.event != "issues"
            or delivery.action != "opened"
            or not isinstance(delivery.payload, GitHubIssuesPayload)
        ):
            return False

        body = delivery.payload.issue.body
        return body is not None and "### Bug description" in body

    async def run(self, delivery: GitHubDelivery) -> None:
        return None
