"""Generic trigger event and workflow run persistence."""

from app.automation.models import TriggerEvent, WorkflowRun, WorkflowRunState

__all__ = ["TriggerEvent", "WorkflowRun", "WorkflowRunState"]
