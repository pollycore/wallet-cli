"""Shared models and constants for the `pw echo` feature."""

from __future__ import annotations

from dataclasses import dataclass


ECHO_SUBJECT = "Echo@Domain"
ALLOWED_ECHO_RESPONSE_FIELDS = frozenset({"Body", "Hash", "Header", "Signature"})
ALLOWED_SYNC_RESPONSE_FIELDS = frozenset({"Meta", "Request", "Response"})


@dataclass(frozen = True)
class _EchoCommandSuccess:
    """Resolved echo command data ready for final rendering."""

    normalized_domain: str
    response_payload: str
    parsed_response_payload: object
    outbound_payload: object | None
    verification_lines: dict[str, str]
    dns_diagnostics: object | None
    dns_link_context: tuple[str, str] | None
    response_metadata: object | None
    transport_metadata: dict[str, object]
    total_seconds: float
    network_seconds: float
    footer_panel: object | None
    client_timeout_seconds: float | None = None


@dataclass(frozen = True)
class _EchoCommandFailure:
    """Resolved echo failure data ready for debug rendering."""

    normalized_domain: str
    error_lines: dict[str, str]
    outbound_payload: object | None
    response_payload: str | None
    parsed_response_payload: object | None
    verification_lines: dict[str, str]
    dns_diagnostics: object | None
    dns_link_context: tuple[str, str] | None
    response_metadata: object | None
    transport_metadata: dict[str, object]
    total_seconds: float
    network_seconds: float
    footer_panel: object
    client_timeout_seconds: float | None = None
