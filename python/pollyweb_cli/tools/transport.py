"""Signing and transport helpers shared by CLI commands."""

from __future__ import annotations

import base64
import hashlib
import json
import urllib.request

from pollyweb import KeyPair, Msg, Struct

from pollyweb_cli.tools.debug import parse_debug_payload, print_debug_payload


def build_signed_message(
    subject: str,
    body: dict[str, object],
    key_pair: KeyPair,
    domain: str,
    from_value: str | None = "Anonymous",
    schema_value: str | None = "pollyweb.org/MSG:1.0"
) -> dict[str, object]:
    """Build a signed PollyWeb request payload for a domain command."""

    message_kwargs: dict[str, str | dict[str, object]] = {
        "To": domain,
        "Subject": subject,
        "Body": body,
    }
    if from_value is not None:
        message_kwargs["From"] = from_value
    if schema_value is not None:
        message_kwargs["Schema"] = schema_value

    # Preserve the existing custom-signing behavior for partial headers.
    if from_value is None or schema_value is None:
        template_message = Msg(**message_kwargs)
        header = {
            "To": template_message.To,
            "Subject": template_message.Subject,
            "Correlation": template_message.Correlation,
            "Timestamp": template_message.Timestamp,
        }
        if from_value is not None:
            header["From"] = template_message.From
        if schema_value is not None:
            header["Schema"] = template_message.Schema

        signed_payload = {
            "Header": header,
            # Convert Struct wrappers back into plain JSON-compatible values.
            "Body": Struct.unwrap(template_message.Body),
        }
        canonical = json.dumps(
            signed_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return {
            **signed_payload,
            "Hash": hashlib.sha256(canonical).hexdigest(),
            "Signature": base64.b64encode(
                key_pair.PrivateKey.sign(canonical)
            ).decode("ascii"),
        }

    message = Msg(**message_kwargs).sign(key_pair.PrivateKey)
    return message.to_dict()


def send_request_message(
    domain: str,
    request_message: dict[str, object],
    debug: bool = False
) -> str:
    """POST a request payload to a PollyWeb inbox and return the response body."""

    request_payload = json.dumps(request_message, separators=(",", ":"))
    request_url = f"https://pw.{domain}/inbox"

    if debug:
        print_debug_payload(f"Outbound payload to {request_url}", request_message)

    request = urllib.request.Request(
        request_url,
        data=request_payload.encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        response_payload = response.read().decode("utf-8")

    if debug:
        print_debug_payload("Inbound payload", parse_debug_payload(response_payload))

    return response_payload


def post_signed_message(
    domain: str,
    subject: str,
    body: dict[str, object],
    key_pair: KeyPair,
    debug: bool = False,
    from_value: str | None = "Anonymous",
    schema_value: str | None = "pollyweb.org/MSG:1.0"
) -> str:
    """Build and send a signed message to a PollyWeb inbox."""

    request_message = build_signed_message(
        subject=subject,
        body=body,
        key_pair=key_pair,
        domain=domain,
        from_value=from_value,
        schema_value=schema_value,
    )
    return send_request_message(
        domain=domain,
        request_message=request_message,
        debug=debug,
    )
