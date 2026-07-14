from datetime import datetime

from pydantic import AnyHttpUrl

from app.automation.repository import TriggerEventData
from app.webhooks.github.models import (
    GitHubDelivery,
    GitHubIssuesPayload,
    GitHubPingPayload,
)


def to_trigger_event(
    delivery: GitHubDelivery,
    received_at: datetime,
) -> TriggerEventData:
    payload = delivery.payload
    if isinstance(payload, GitHubIssuesPayload):
        return TriggerEventData(
            source="github",
            external_id=delivery.delivery_id,
            event_type=delivery.event,
            action=delivery.action,
            subject_type="issue",
            subject_id=f"{payload.repository.full_name}#{payload.issue.number}",
            subject_title=payload.issue.title,
            subject_url=AnyHttpUrl(payload.issue.html_url),
            received_at=received_at,
        )

    if isinstance(payload, GitHubPingPayload):
        return TriggerEventData(
            source="github",
            external_id=delivery.delivery_id,
            event_type=delivery.event,
            action=None,
            subject_type="repository",
            subject_id=payload.repository.full_name,
            subject_title=payload.repository.full_name,
            subject_url=None,
            received_at=received_at,
        )

    return TriggerEventData(
        source="github",
        external_id=delivery.delivery_id,
        event_type=delivery.event,
        action=None,
        subject_type=None,
        subject_id=None,
        subject_title=None,
        subject_url=None,
        received_at=received_at,
    )
