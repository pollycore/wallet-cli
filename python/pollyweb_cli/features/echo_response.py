"""Response parsing and error translation helpers for `pw echo`."""

from __future__ import annotations

import inspect
import json
import socket
import urllib.error

from pollyweb import Msg, MsgValidationError

from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.features.bind import describe_bind_network_error
from pollyweb_cli.features.echo_models import (
    ALLOWED_ECHO_RESPONSE_FIELDS,
    ALLOWED_SYNC_RESPONSE_FIELDS,
)
from pollyweb_cli.tools.debug import parse_debug_payload


def _coerce_echo_response_metadata(
    metadata: object
) -> dict[str, object] | None:
    """Return echo response metadata as a plain mapping when available."""

    if isinstance(metadata, dict):
        return metadata

    if hasattr(metadata, "get"):
        coerced: dict[str, object] = {}
        found_value = False

        for key in (
            "LatencyMs",
            "ColdMs",
            "TotalMs",
            "HandlerMs",
            "TotalExecutionMs",
            "DownstreamExecutionMs",
        ):
            value = metadata.get(key)
            if value is not None:
                coerced[key] = value
                found_value = True

        if found_value:
            return coerced

    return None


def _merge_echo_response_metadata(
    *metadata_values: object
) -> dict[str, object] | None:
    """Merge timing metadata from the supported echo response locations."""

    merged_metadata: dict[str, object] = {}

    for metadata in metadata_values:
        coerced_metadata = _coerce_echo_response_metadata(metadata)
        if coerced_metadata is None:
            continue

        for key, value in coerced_metadata.items():
            merged_metadata[key] = value

    if not merged_metadata:
        return None

    return merged_metadata


def _extract_echo_response_metadata(
    response_payload: str,
    response: Msg
) -> dict[str, object] | None:
    """Collect timing metadata from wrapped sync replies and reply bodies."""

    payload_metadata: object | None = None
    response_wrapper_metadata: object | None = None

    try:
        loaded_payload = json.loads(response_payload)
    except json.JSONDecodeError:
        loaded_payload = None

    if isinstance(loaded_payload, dict):
        payload_metadata = loaded_payload.get("Meta")

        wrapped_response = loaded_payload.get("Response")
        if isinstance(wrapped_response, dict):
            response_wrapper_metadata = wrapped_response.get("Meta")

    response_body_metadata = None
    if hasattr(response.Body, "get"):
        response_body_metadata = response.Body.get("Metadata")

    return _merge_echo_response_metadata(
        payload_metadata,
        response_wrapper_metadata,
        response_body_metadata,
    )


def _to_echo_user_facing_error(
    exc: MsgValidationError,
    *,
    domain: str
) -> UserFacingError:
    """Translate library verification failures into echo-specific CLI wording."""

    message = str(exc)
    diagnostics = getattr(exc, "dns_diagnostics", None)

    if message.startswith("Unexpected top-level field(s):"):
        lowered_message = message[0].lower() + message[1:]
        return UserFacingError(
            f"Echo response from {domain} had {lowered_message}",
            diagnostics = diagnostics)

    if message.startswith("Unexpected "):
        return UserFacingError(
            f"Echo response from {domain} had an {message[0].lower() + message[1:]}",
            diagnostics = diagnostics)

    return UserFacingError(
        f"Echo response from {domain} did not verify: {message}",
        diagnostics = diagnostics)


def _rewrite_echo_request_validation_error(
    exc: MsgValidationError
) -> str:
    """Return echo-specific wording for request-construction validation errors."""

    message = str(exc)

    if message == "To must be a domain string or a UUID":
        return "To must be a domain string."

    return message


def _build_echo_failure_verification_lines(
    response_payload: str | None
) -> dict[str, str]:
    """Build best-effort reply details for debug failure output."""

    if response_payload is None:
        return {}

    payload = parse_debug_payload(response_payload)
    if not isinstance(payload, dict):
        return {}

    response = payload.get("Response")
    if isinstance(response, dict):
        header = response.get("Header")
        signed_payload = response
    else:
        header = payload.get("Header")
        signed_payload = payload

    if not isinstance(header, dict):
        header = {}

    verification_lines: dict[str, str] = {}
    schema = header.get("Schema")
    if isinstance(schema, str) and schema:
        verification_lines["Schema reported"] = schema

    if isinstance(signed_payload.get("Hash"), str) and signed_payload["Hash"]:
        verification_lines["Canonical payload hash"] = "present in the reply"
    else:
        verification_lines["Canonical payload hash"] = "missing from the reply"

    selector = header.get("Selector")
    signature = signed_payload.get("Signature")
    if isinstance(signature, str) and signature:
        if isinstance(selector, str) and selector:
            verification_lines["Signature field"] = (
                f"present in the reply (selector {selector})"
            )
        else:
            verification_lines["Signature field"] = "present in the reply"
    else:
        verification_lines["Signature field"] = "missing from the reply"

    for key, label in (
        ("From", "From reported by reply"),
        ("To", "To reported by reply"),
        ("Subject", "Subject reported by reply"),
        ("Correlation", "Correlation reported by reply"),
    ):
        value = header.get(key)
        if isinstance(value, str) and value:
            verification_lines[label] = value

    return verification_lines


def _parse_echo_response(
    response_payload: str,
    normalized_domain: str
) -> Msg:
    """Parse an echo response, supporting both direct and wrapped sync payloads."""

    parse_parameters = inspect.signature(Msg.parse).parameters
    if "sync_response" in parse_parameters:
        return Msg.parse(
            response_payload,
            sync_response = True)

    try:
        loaded_payload = json.loads(response_payload)
    except json.JSONDecodeError:
        return Msg.parse(
            response_payload,
            allowed_top_level_fields = ALLOWED_ECHO_RESPONSE_FIELDS)

    if not isinstance(loaded_payload, dict):
        return Msg.parse(
            response_payload,
            allowed_top_level_fields = ALLOWED_ECHO_RESPONSE_FIELDS)

    if "Response" not in loaded_payload:
        return Msg.parse(
            loaded_payload,
            allowed_top_level_fields = ALLOWED_ECHO_RESPONSE_FIELDS)

    unexpected_fields = sorted(
        field
        for field in loaded_payload
        if field not in ALLOWED_SYNC_RESPONSE_FIELDS
    )
    if unexpected_fields:
        allowed_fields = "Meta, Request, and Response"
        unexpected = ", ".join(unexpected_fields)
        raise UserFacingError(
            f"Echo response from {normalized_domain} had unexpected "
            f"top-level field(s): {unexpected}. Expected only {allowed_fields}."
        )

    response_message = loaded_payload.get("Response")
    if isinstance(response_message, dict) and "Meta" in response_message:
        response_message = {
            key: value
            for key, value in response_message.items()
            if key != "Meta"
        }

    return Msg.parse(
        response_message,
        allowed_top_level_fields = ALLOWED_ECHO_RESPONSE_FIELDS)


def _describe_echo_network_error(
    domain: str,
    reason: object,
    *,
    debug: bool
) -> str:
    """Format echo transport failures for either normal or debug output."""

    if isinstance(reason, socket.gaierror):
        friendly = (
            f"Could not resolve domain name {domain}. "
            "Check that the domain name is correct and that its DNS record exists."
        )
        if debug:
            return f"{friendly} ({reason})"
        return friendly

    if debug:
        if isinstance(reason, str):
            return reason

        return repr(reason)

    return describe_bind_network_error(
        domain,
        reason)


def _describe_http_echo_error(exc: urllib.error.HTTPError) -> str:
    """Build the user-facing HTTP failure message for `pw echo`."""

    message = f"The server returned HTTP {exc.code}."
    error_body = getattr(exc, "pollyweb_error_body", None)

    if not isinstance(error_body, str) or not error_body.strip():
        return message

    try:
        parsed_body = parse_debug_payload(error_body)
    except Exception:
        parsed_body = None

    if isinstance(parsed_body, dict):
        error_value = parsed_body.get("error")
        if isinstance(error_value, str) and error_value.strip():
            return f"{message} {error_value}"

    return message
