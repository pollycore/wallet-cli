"""Message file loading and send command implementation."""

from __future__ import annotations

from pathlib import Path
import urllib.error

from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.tools.transport import build_signed_message, send_request_message

import yaml


def load_message_request(path: Path) -> dict[str, object]:
    """Load one message request from a YAML or JSON file path."""

    try:
        loaded = yaml.safe_load(path.read_text(encoding = "utf-8"))
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise UserFacingError(
            f"Could not read message file {path}: {exc}"
        ) from None

    if not isinstance(loaded, dict):
        raise UserFacingError(
            f"Message file {path} must contain a YAML or JSON object."
        ) from None

    body = loaded.get("Body", {})
    header = loaded.get("Header")

    # Support both the simple top-level shape and a Header/Body envelope.
    if isinstance(header, dict):
        normalized = {
            "To": header.get("To"),
            "Subject": header.get("Subject"),
            "From": header.get("From"),
            "Schema": header.get("Schema"),
            "Body": body,
        }
    else:
        normalized = {
            "To": loaded.get("To"),
            "Subject": loaded.get("Subject"),
            "From": loaded.get("From"),
            "Schema": loaded.get("Schema"),
            "Body": body,
        }

    to_value = normalized.get("To")
    if not isinstance(to_value, str) or not to_value.strip():
        raise UserFacingError(
            f"Message file {path} must include a string To value."
        ) from None

    subject_value = normalized.get("Subject")
    if not isinstance(subject_value, str) or not subject_value.strip():
        raise UserFacingError(
            f"Message file {path} must include a string Subject value."
        ) from None

    if not isinstance(body, dict):
        raise UserFacingError(
            f"Message file {path} must include Body as an object when present."
        ) from None

    from_value = normalized.get("From")
    if from_value is not None and not isinstance(from_value, str):
        raise UserFacingError(
            f"Message file {path} must use a string From value when present."
        ) from None

    schema_value = normalized.get("Schema")
    if schema_value is not None and not isinstance(schema_value, str):
        raise UserFacingError(
            f"Message file {path} must use a string Schema value when present."
        ) from None

    return normalized


def cmd_msg(
    path: Path,
    *,
    debug: bool,
    config_dir: Path,
    require_configured_keys,
    load_signing_key_pair
) -> int:
    """Load, sign, send, and print the response for one message file."""

    try:
        require_configured_keys()
        key_pair = load_signing_key_pair()
        request = load_message_request(path)

        request_message = build_signed_message(
            subject = str(request["Subject"]),
            body = dict(request["Body"]),
            key_pair = key_pair,
            domain = str(request["To"]),
            from_value = request.get("From"),
            schema_value = request.get("Schema"),
        )

        response_payload = send_request_message(
            domain = str(request["To"]),
            request_message = request_message,
            debug = debug,
        )
    except FileNotFoundError:
        if not path.exists():
            raise UserFacingError(f"Message file not found: {path}") from None
        raise UserFacingError(
            f"Missing PollyWeb keys in {config_dir}. Run `pw config` first."
        ) from None
    except urllib.error.HTTPError as exc:
        raise UserFacingError(
            f"Message request from {path} failed with HTTP {exc.code}."
        ) from None
    except urllib.error.URLError as exc:
        reason = exc.reason if isinstance(exc.reason, str) else repr(exc.reason)
        raise UserFacingError(
            f"Message request from {path} failed: {reason}"
        ) from None

    print(response_payload)
    return 0
