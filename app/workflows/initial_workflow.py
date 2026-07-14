from app.github.webhooks.models import GitHubDelivery


class InitialWorkflow:
    """Placeholder for the first GitHub-to-Devin workflow."""

    name = "initial-workflow"

    def matches(self, delivery: GitHubDelivery) -> bool:
        return False

    async def run(self, delivery: GitHubDelivery) -> None:
        return None
