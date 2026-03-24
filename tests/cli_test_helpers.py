"""Shared helpers for the split CLI test modules."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pollyweb._crypto import encode_signature, sign_message, signature_algorithm_for_private_key


VALID_BIND = "Bind:123e4567-e89b-12d3-a456-426614174000"
VALID_WALLET_ID = "123e4567-e89b-12d3-a456-426614174000"
TEST_MSGS_DIR = Path(__file__).resolve().parents[1] / "test-msgs"


class DummyResponse:
    """Minimal urlopen-style response wrapper for CLI tests."""

    def __init__(
        self,
        payload: bytes,
        *,
        headers: dict[str, str] | None = None
    ):
        self._payload = payload
        self.headers = headers or {}

    def read(self) -> bytes:
        """Return the fixed payload body."""

        return self._payload

    def __enter__(self):
        """Support context-manager use in urllib wrappers."""

        return self

    def __exit__(self, exc_type, exc, tb):
        """Leave exceptions untouched when exiting the context manager."""

        return False


def make_echo_response_payload(
    *,
    from_value: str,
    correlation: str,
    private_key,
    to_value: str | None = None,
    selector: str = "default",
    body: dict[str, object] | None = None,
) -> bytes:
    """Build one signed echo response payload for CLI transport tests."""

    # Domain-signed replies omit Header.Algorithm and let receivers infer it
    # from DKIM, matching the published PollyWeb wire contract.
    header = {
        "Correlation": correlation,
        "From": from_value,
        "Schema": "pollyweb.org/MSG:1.0",
        "Selector": selector,
        "Subject": "Echo@Domain",
        "Timestamp": "2026-03-17T20:00:00.000Z",
        "To": from_value if to_value is None else to_value,
    }
    canonical_payload = {
        "Body": body or {"Echo": "ok"},
        "Header": header,
    }
    canonical = json.dumps(
        canonical_payload,
        sort_keys = True,
        separators = (",", ":"),
        ensure_ascii = False,
    ).encode("utf-8")
    signature, _ = sign_message(
        private_key,
        canonical,
        signature_algorithm = signature_algorithm_for_private_key(private_key),
    )
    payload = {
        **canonical_payload,
        "Hash": hashlib.sha256(canonical).hexdigest(),
        "Signature": encode_signature(signature),
    }
    return json.dumps(payload).encode("utf-8")


class FakeReadline:
    """Tiny readline stub that records history interactions."""

    def __init__(self):
        self.history: list[str] = []
        self.history_length = None

    def clear_history(self):
        """Clear any stored command history."""

        self.history.clear()

    def add_history(self, item: str):
        """Record one history entry."""

        self.history.append(item)

    def set_history_length(self, length: int):
        """Store the requested history cap."""

        self.history_length = length


class FakeChatConnection:
    """Small chat connection stub used by CLI command tests."""

    def __init__(self, notifier_domain: str, wallet_id: str, auth_token: str):
        self.notifier_domain = notifier_domain
        self.wallet_id = wallet_id
        self.auth_token = auth_token
        self.calls: list[str] = []

    def connect(self) -> None:
        """Record the connection step."""

        self.calls.append("connect")

    def subscribe(self) -> None:
        """Record the subscription step."""

        self.calls.append("subscribe")

    def publish(self, event: object) -> None:
        """Record one published event."""

        self.calls.append(f"publish:{event}")

    def listen_forever(self) -> None:
        """Stop the loop by simulating a keyboard interrupt."""

        self.calls.append("listen")
        raise KeyboardInterrupt()

    def close(self) -> None:
        """Record connection shutdown."""

        self.calls.append("close")
