import logging
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, ValidationError

from app.config import GitHubWebhookSettings
from app.webhooks.github.models import (
    GitHubWebhookHeaders,
    parse_github_delivery,
)
from app.webhooks.github.security import (
    GitHubWebhookVerifier,
    InvalidGitHubSignatureError,
)
from app.workflows.dispatcher import WorkflowDispatcher

logger = logging.getLogger(__name__)


class GitHubWebhookAcknowledgement(BaseModel):
    """Response confirming receipt without claiming workflow execution."""

    model_config = ConfigDict(extra="forbid", strict=True)

    delivery_id: str
    event: str
    action: str | None
    repository: str | None
    status: Literal["received", "ignored"]


def create_github_webhook_router(
    settings: GitHubWebhookSettings,
    dispatcher: WorkflowDispatcher,
) -> APIRouter:
    router = APIRouter(prefix="/api/webhooks/github", tags=["github-webhooks"])
    secret = settings.github_webhook_secret
    verifier = (
        GitHubWebhookVerifier(secret)
        if secret is not None and secret.get_secret_value()
        else None
    )

    @router.post(
        "",
        response_model=GitHubWebhookAcknowledgement,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def receive_github_webhook(
        request: Request,
        background_tasks: BackgroundTasks,
        signature: Annotated[
            str | None,
            Header(alias="X-Hub-Signature-256"),
        ] = None,
        event: Annotated[str | None, Header(alias="X-GitHub-Event")] = None,
        delivery_id: Annotated[
            str | None,
            Header(alias="X-GitHub-Delivery"),
        ] = None,
    ) -> GitHubWebhookAcknowledgement:
        content_type = request.headers.get("content-type")
        media_type = (
            content_type.partition(";")[0].strip().lower()
            if content_type is not None
            else None
        )
        if media_type != "application/json":
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="GitHub webhook content type must be application/json",
            )

        if verifier is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GitHub webhook secret is not configured",
            )

        if signature is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="GitHub webhook signature is missing",
            )

        if event is None or delivery_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Required GitHub delivery headers are missing",
            )

        raw_body = await request.body()
        try:
            verifier.verify(raw_body, signature)
        except InvalidGitHubSignatureError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="GitHub webhook signature is invalid",
            ) from error

        try:
            headers = GitHubWebhookHeaders(
                delivery_id=delivery_id,
                event=event,
            )
            delivery = parse_github_delivery(headers, raw_body)
        except ValidationError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub webhook payload or headers are invalid",
            ) from error

        delivery_status: Literal["received", "ignored"] = (
            "received" if delivery.event in {"issues", "ping"} else "ignored"
        )
        logger.info(
            "Received GitHub webhook",
            extra={
                "github_delivery_id": delivery.delivery_id,
                "github_event": delivery.event,
                "github_action": delivery.action,
                "github_repository": delivery.repository,
                "github_delivery_status": delivery_status,
            },
        )
        # This in-process handoff is intentionally non-durable for the current service.
        # Use durable execution in production so accepted deliveries survive termination.
        background_tasks.add_task(dispatcher.dispatch, delivery)
        return GitHubWebhookAcknowledgement(
            delivery_id=delivery.delivery_id,
            event=delivery.event,
            action=delivery.action,
            repository=delivery.repository,
            status=delivery_status,
        )

    return router
