"""Message file loading and send command implementation."""

from __future__ import annotations

import json
from pathlib import Path
import runpy
import socket
import urllib.error

from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.tools.transport import build_signed_message, send_request_message

import yaml


HEADER_FIELDS = {
    "To",
    "Subject",
    "From",
    "Schema",
    "Body",
    "Header",
}
INLINE_HEADER_FIELD_MAP = {
    "to": "To",
    "subject": "Subject",
    "from": "From",
    "schema": "Schema",
    "body": "Body",
    "header": "Header",
}
MESSAGE_FILE_SUFFIXES = {
    ".yaml",
    ".yml",
    ".json",
    ".py",
}
POLLYWEB_DOMAIN_ALIAS_SUFFIX = ".dom"
POLLYWEB_DOMAIN_CANONICAL_SUFFIX = ".pollyweb.org"


def _normalize_loaded_message(
    loaded: object,
    source_name: str
) -> dict[str, object]:
    """Normalize one loaded message object into the request shape."""

    if not isinstance(loaded, dict):
        raise UserFacingError(
            f"{source_name} must contain a YAML or JSON object."
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
            f"{source_name} must include a string To value."
        ) from None

    subject_value = normalized.get("Subject")
    if not isinstance(subject_value, str) or not subject_value.strip():
        raise UserFacingError(
            f"{source_name} must include a string Subject value."
        ) from None

    if not isinstance(body, dict):
        raise UserFacingError(
            f"{source_name} must include Body as an object when present."
        ) from None

    from_value = normalized.get("From")
    if from_value is not None and not isinstance(from_value, str):
        raise UserFacingError(
            f"{source_name} must use a string From value when present."
        ) from None

    schema_value = normalized.get("Schema")
    if schema_value is not None and not isinstance(schema_value, str):
        raise UserFacingError(
            f"{source_name} must use a string Schema value when present."
        ) from None

    normalized["To"] = normalize_message_domain(str(to_value))

    return normalized


def normalize_message_domain(domain: str) -> str:
    """Expand supported domain aliases used by `pw msg`."""

    stripped = domain.strip()
    if stripped.endswith(POLLYWEB_DOMAIN_ALIAS_SUFFIX):
        return (
            stripped[: -len(POLLYWEB_DOMAIN_ALIAS_SUFFIX)]
            + POLLYWEB_DOMAIN_CANONICAL_SUFFIX
        )
    return stripped


def load_message_request(path: Path) -> dict[str, object]:
    """Load one message request from a YAML, JSON, or Python file path."""

    try:
        if path.suffix == ".py":
            loaded = load_python_message_request(path)
        else:
            loaded = yaml.safe_load(path.read_text(encoding = "utf-8"))
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise UserFacingError(
            f"Could not read message file {path}: {exc}"
        ) from None

    return _normalize_loaded_message(loaded, f"Message file {path}")


def load_python_message_request(path: Path) -> object:
    """Load one message request object from a Python file."""

    namespace = runpy.run_path(str(path))

    # Allow a small set of explicit names so Python files stay predictable.
    for variable_name in ("MESSAGE", "message", "REQUEST", "request"):
        if variable_name in namespace:
            return namespace[variable_name]

    builder = namespace.get("build_message")
    if callable(builder):
        return builder()

    raise UserFacingError(
        f"Python message file {path} must define MESSAGE, message, "
        "REQUEST, request, or build_message()."
    ) from None


def parse_inline_message_arguments(arguments: list[str]) -> dict[str, object]:
    """Parse inline `Key:Value` message arguments into the request shape."""

    request: dict[str, object] = {}
    body: dict[str, object] = {}

    for argument in arguments:
        if ":" not in argument:
            raise UserFacingError(
                "Inline message arguments must use Key:Value pairs."
            ) from None

        key, raw_value = argument.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()

        if not key:
            raise UserFacingError(
                "Inline message arguments must include a non-empty key."
            ) from None

        value = yaml.safe_load(raw_value)

        normalized_key = INLINE_HEADER_FIELD_MAP.get(key.lower(), key)

        if normalized_key in HEADER_FIELDS:
            request[normalized_key] = value
            continue

        body[key] = value

    if body:
        request["Body"] = body

    return _normalize_loaded_message(request, "Inline message arguments")


def parse_message_request(arguments: list[str]) -> tuple[dict[str, object], str]:
    """Parse a message request from a file path, JSON string, or inline pairs."""

    if len(arguments) == 1:
        candidate = arguments[0]
        candidate_path = Path(candidate)

        if candidate_path.exists() or candidate_path.suffix in MESSAGE_FILE_SUFFIXES:
            return load_message_request(candidate_path), str(candidate_path)

        if candidate.lstrip().startswith("{"):
            try:
                loaded = json.loads(candidate)
            except json.JSONDecodeError as exc:
                raise UserFacingError(
                    f"Could not parse JSON message argument: {exc.msg}"
                ) from None

            return _normalize_loaded_message(loaded, "JSON message argument"), candidate

    return parse_inline_message_arguments(arguments), "inline message arguments"


def describe_message_network_error(
    domain: str,
    reason: object
) -> str:
    """Convert a transport failure into a human-readable message."""

    if isinstance(reason, socket.gaierror):
        return f"Could not resolve PollyWeb inbox host pw.{domain}"

    if isinstance(reason, str):
        return reason

    return repr(reason)


def cmd_msg(
    arguments: list[str],
    *,
    debug: bool,
    config_dir: Path,
    require_configured_keys,
    load_signing_key_pair
) -> int:
    """Load, sign, send, and print the response for one message input."""

    source_name = "message input"

    try:
        require_configured_keys()
        key_pair = load_signing_key_pair()
        request, source_name = parse_message_request(arguments)

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
        if len(arguments) == 1 and Path(arguments[0]).suffix in MESSAGE_FILE_SUFFIXES:
            raise UserFacingError(
                f"Message file not found: {arguments[0]}"
            ) from None
        raise UserFacingError(
            f"Missing PollyWeb keys in {config_dir}. Run `pw config` first."
        ) from None
    except urllib.error.HTTPError as exc:
        raise UserFacingError(
            f"Message request from {source_name} failed with HTTP {exc.code}."
        ) from None
    except urllib.error.URLError as exc:
        reason = describe_message_network_error(
            str(request["To"]),
            exc.reason)
        raise UserFacingError(
            f"Message request from {source_name} failed: {reason}"
        ) from None

    print(response_payload)
    return 0
