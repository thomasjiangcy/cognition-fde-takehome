import hashlib
import hmac

from pydantic import SecretStr


class InvalidGitHubSignatureError(Exception):
    """Raised when a delivery does not carry GitHub's expected HMAC."""


class GitHubWebhookVerifier:
    """Verify GitHub's HMAC-SHA256 signature over unchanged request bytes."""

    def __init__(self, secret: SecretStr) -> None:
        secret_value = secret.get_secret_value()
        if not secret_value:
            raise ValueError("GitHub webhook secret cannot be empty")
        self._secret = secret_value.encode("utf-8")

    def verify(self, raw_body: bytes, signature_header: str) -> None:
        expected_signature = (
            "sha256="
            + hmac.new(
                self._secret,
                raw_body,
                hashlib.sha256,
            ).hexdigest()
        )
        if not hmac.compare_digest(expected_signature, signature_header):
            raise InvalidGitHubSignatureError
