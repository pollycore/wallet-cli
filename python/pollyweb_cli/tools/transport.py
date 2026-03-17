"""Wallet-backed message helpers shared by CLI commands."""

from __future__ import annotations

import json

from pollyweb import KeyPair, Msg, Wallet, normalize_domain_name

from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.tools.debug import parse_debug_payload, print_debug_payload


DEFAULT_SCHEMA = "pollyweb.org/MSG:1.0"


def serialize_wallet_response(response: object) -> str:
    """Convert a PollyWeb response object into the CLI's raw string form."""

    if isinstance(response, Msg):
        return json.dumps(response.to_dict(), separators=(",", ":"))
    if isinstance(response, dict):
        return json.dumps(response, separators=(",", ":"))
    return str(response)


def build_wallet_message(
    domain: str,
    subject: str,
    body: dict[str, object],
    key_pair: KeyPair,
    from_value: str | None = "Anonymous",
    schema_value: str | None = DEFAULT_SCHEMA
) -> tuple[Wallet, Msg, str]:
    """Create a wallet sender and normalized PollyWeb message."""

    normalized_domain = normalize_domain_name(domain)
    sender_value = "Anonymous" if from_value in (None, "") else str(from_value)

    try:
        wallet = Wallet(KeyPair=key_pair, ID=sender_value)
    except ValueError:
        raise UserFacingError(
            "Wallet-backed commands only support `From: Anonymous` or a UUID bind value."
        ) from None

    message_kwargs: dict[str, object] = {
        "To": normalized_domain,
        "Subject": subject,
        "Body": body,
    }
    if schema_value is not None:
        message_kwargs["Schema"] = schema_value

    return wallet, Msg(**message_kwargs), normalized_domain


def send_wallet_message(
    domain: str,
    subject: str,
    body: dict[str, object],
    key_pair: KeyPair,
    debug: bool = False,
    from_value: str | None = "Anonymous",
    schema_value: str | None = DEFAULT_SCHEMA
) -> tuple[str, Msg, str]:
    """Send one wallet-backed PollyWeb message and return the raw response."""

    wallet, request_message, normalized_domain = build_wallet_message(
        domain=domain,
        subject=subject,
        body=body,
        key_pair=key_pair,
        from_value=from_value,
        schema_value=schema_value,
    )

    if debug:
        request_url = f"https://pw.{normalized_domain}/inbox"
        print_debug_payload(
            f"Outbound payload to {request_url}",
            wallet.sign(request_message).to_dict(),
        )

    response = wallet.send(request_message)
    response_payload = serialize_wallet_response(response)

    if debug:
        print_debug_payload("Inbound payload", parse_debug_payload(response_payload))

    return response_payload, request_message, normalized_domain
