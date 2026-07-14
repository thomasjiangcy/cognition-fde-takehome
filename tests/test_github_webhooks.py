import hashlib
import hmac

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.config import GitHubWebhookSettings
from app.webhooks.github.router import create_github_webhook_router
from app.webhooks.github.security import (
    GitHubWebhookVerifier,
    InvalidGitHubSignatureError,
)

# These requests simulate only GitHub's external webhook boundary. Header and
# payload fields follow GitHub's official contracts:
# https://docs.github.com/en/webhooks/webhook-events-and-payloads#issues
# https://docs.github.com/en/webhooks/webhook-events-and-payloads#ping
# Signature test vector and algorithm:
# https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries#testing-the-webhook-payload-validation

WEBHOOK_SECRET = "correct horse battery staple"

ISSUES_OPENED_PAYLOAD = b"""{
  "action": "opened",
  "issue": {
    "id": 1347,
    "number": 1347,
    "title": "Mixed Chart matrixify does not apply to Query B",
    "body": "The dimension only applies to Query A.",
    "state": "open",
    "html_url": "https://github.com/octocat/Hello-World/issues/1347",
    "user": {"id": 1, "login": "octocat"},
    "labels": [
      {
        "id": 10,
        "name": "validation:required",
        "color": "D93F0B",
        "description": "A committer should validate the issue"
      }
    ]
  },
  "repository": {
    "id": 1296269,
    "full_name": "octocat/Hello-World",
    "private": false,
    "html_url": "https://github.com/octocat/Hello-World"
  },
  "sender": {"id": 1, "login": "octocat"}
}"""

PING_PAYLOAD = b"""{
  "zen": "Keep it logically awesome.",
  "hook_id": 123456,
  "repository": {
    "id": 1296269,
    "full_name": "octocat/Hello-World",
    "private": false,
    "html_url": "https://github.com/octocat/Hello-World"
  },
  "sender": {"id": 1, "login": "octocat"}
}"""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _signature(raw_body: bytes) -> str:
    digest = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def _headers(event: str, raw_body: bytes) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-GitHub-Delivery": "72d3162e-cc78-11e3-81ab-4c9367dc0958",
        "X-GitHub-Event": event,
        "X-Hub-Signature-256": _signature(raw_body),
    }


def _webhook_app(secret: str | None = WEBHOOK_SECRET) -> FastAPI:
    app = FastAPI()
    settings = GitHubWebhookSettings(
        github_webhook_secret=SecretStr(secret) if secret is not None else None,
    )
    app.include_router(create_github_webhook_router(settings))
    return app


@pytest.mark.anyio
async def test_receives_verified_issues_delivery() -> None:
    transport = ASGITransport(app=_webhook_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/webhooks/github",
            content=ISSUES_OPENED_PAYLOAD,
            headers=_headers("issues", ISSUES_OPENED_PAYLOAD),
        )

    assert response.status_code == 202
    assert response.json() == {
        "delivery_id": "72d3162e-cc78-11e3-81ab-4c9367dc0958",
        "event": "issues",
        "action": "opened",
        "repository": "octocat/Hello-World",
        "status": "received",
    }


@pytest.mark.anyio
async def test_receives_webhook_registration_ping() -> None:
    transport = ASGITransport(app=_webhook_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/webhooks/github",
            content=PING_PAYLOAD,
            headers=_headers("ping", PING_PAYLOAD),
        )

    assert response.status_code == 202
    assert response.json()["event"] == "ping"
    assert response.json()["status"] == "received"


@pytest.mark.anyio
async def test_rejects_invalid_signature_before_parsing_payload() -> None:
    invalid_json = b"not JSON"
    headers = _headers("issues", invalid_json)
    headers["X-Hub-Signature-256"] = "sha256=invalid"
    transport = ASGITransport(app=_webhook_app())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/webhooks/github",
            content=invalid_json,
            headers=headers,
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "GitHub webhook signature is invalid"}


@pytest.mark.anyio
async def test_rejects_missing_signature() -> None:
    headers = _headers("issues", ISSUES_OPENED_PAYLOAD)
    del headers["X-Hub-Signature-256"]
    transport = ASGITransport(app=_webhook_app())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/webhooks/github",
            content=ISSUES_OPENED_PAYLOAD,
            headers=headers,
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "GitHub webhook signature is missing"}


@pytest.mark.anyio
async def test_rejects_invalid_issues_payload_after_verification() -> None:
    invalid_payload = b'{"action":"opened"}'
    transport = ASGITransport(app=_webhook_app())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/webhooks/github",
            content=invalid_payload,
            headers=_headers("issues", invalid_payload),
        )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "GitHub webhook payload or headers are invalid"
    }


@pytest.mark.anyio
async def test_rejects_delivery_when_secret_is_not_configured() -> None:
    transport = ASGITransport(app=_webhook_app(secret=None))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/webhooks/github",
            content=ISSUES_OPENED_PAYLOAD,
            headers=_headers("issues", ISSUES_OPENED_PAYLOAD),
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "GitHub webhook secret is not configured"}


@pytest.mark.anyio
async def test_ignores_verified_unsubscribed_event() -> None:
    payload = b"{}"
    transport = ASGITransport(app=_webhook_app())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/webhooks/github",
            content=payload,
            headers=_headers("push", payload),
        )

    assert response.status_code == 202
    assert response.json() == {
        "delivery_id": "72d3162e-cc78-11e3-81ab-4c9367dc0958",
        "event": "push",
        "action": None,
        "repository": None,
        "status": "ignored",
    }


@pytest.mark.anyio
async def test_rejects_non_json_webhook_configuration() -> None:
    headers = _headers("issues", ISSUES_OPENED_PAYLOAD)
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    transport = ASGITransport(app=_webhook_app())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/webhooks/github",
            content=ISSUES_OPENED_PAYLOAD,
            headers=headers,
        )

    assert response.status_code == 415
    assert response.json() == {
        "detail": "GitHub webhook content type must be application/json"
    }


def test_verifier_matches_github_documented_signature_vector() -> None:
    verifier = GitHubWebhookVerifier(SecretStr("It's a Secret to Everybody"))
    verifier.verify(
        b"Hello, World!",
        "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17",
    )

    with pytest.raises(InvalidGitHubSignatureError):
        verifier.verify(b"Hello, World?", "sha256=757107ea0eb2509f")
