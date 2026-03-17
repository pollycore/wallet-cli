"""Test fixture loading and validation for the `pw test` command."""

from __future__ import annotations

import json
from pathlib import Path
import socket
import urllib.error
from typing import Any

import yaml

from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.features.msg import (
    describe_message_network_error,
    parse_message_request,
)
from pollyweb_cli.tools.transport import build_signed_message, send_request_message


def load_message_test_fixture(
    path: Path
) -> dict[str, Any]:
    """Load and validate a wrapped message test fixture from disk."""

    try:
        loaded = yaml.safe_load(path.read_text(encoding = "utf-8"))
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise UserFacingError(
            f"Could not read test file {path}: {exc}"
        ) from None

    if not isinstance(loaded, dict):
        raise UserFacingError(
            f"Test file {path} must contain a YAML object."
        ) from None

    outbound = loaded.get("Outbound")
    if not isinstance(outbound, dict):
        raise UserFacingError(
            f"Test file {path} must define an `Outbound` object."
        ) from None

    inbound = loaded.get("Inbound")
    if inbound is not None and not isinstance(inbound, dict):
        raise UserFacingError(
            f"Test file {path} must define `Inbound` as an object when present."
        ) from None

    return loaded


def normalize_test_response(
    payload: str,
    source_name: str
) -> dict[str, Any]:
    """Parse the CLI response payload into a mapping used for subset assertions."""

    try:
        loaded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise UserFacingError(
            f"Response from {source_name} was not valid JSON: {exc.msg}."
        ) from None

    if not isinstance(loaded, dict):
        raise UserFacingError(
            f"Response from {source_name} must be a JSON object."
        ) from None

    # Mirror the simpler message-shaped fixtures by surfacing common header
    # values at the top level in addition to the raw Header object.
    header = loaded.get("Header")
    if isinstance(header, dict):
        for key in ("From", "To", "Subject", "Correlation", "Timestamp"):
            if key in header:
                loaded.setdefault(key, header[key])

    return loaded


def assert_expected_subset(
    actual: Any,
    expected: Any,
    location: str
) -> None:
    """Assert that a response contains the expected fixture subset."""

    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise UserFacingError(
                f"Expected {location} to be an object, but got {actual!r}."
            ) from None

        for key, expected_value in expected.items():
            if key not in actual:
                raise UserFacingError(
                    f"Expected {location}.{key} to exist in the response."
                ) from None

            assert_expected_subset(
                actual[key],
                expected_value,
                f"{location}.{key}")
        return

    if actual != expected:
        raise UserFacingError(
            f"Expected {location} to equal {expected!r}, but got {actual!r}."
        ) from None


def cmd_test(
    test_path: str,
    *,
    debug: bool,
    config_dir: Path,
    require_configured_keys,
    load_signing_key_pair
) -> int:
    """Send one wrapped test fixture and verify its expected inbound response."""

    source_name = f"test file {test_path}"

    try:
        require_configured_keys()
        key_pair = load_signing_key_pair()
        fixture_path = Path(test_path)
        fixture = load_message_test_fixture(fixture_path)

        request, _ = parse_message_request(
            [json.dumps(fixture["Outbound"])])

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
        if Path(test_path).suffix in {".yaml", ".yml", ".json"}:
            raise UserFacingError(
                f"Test file not found: {test_path}"
            ) from None
        raise UserFacingError(
            f"Missing PollyWeb keys in {config_dir}. Run `pw config` first."
        ) from None
    except urllib.error.HTTPError as exc:
        raise UserFacingError(
            f"Test request from {source_name} failed with HTTP {exc.code}."
        ) from None
    except urllib.error.URLError as exc:
        reason = describe_message_network_error(
            str(request["To"]),
            exc.reason)
        raise UserFacingError(
            f"Test request from {source_name} failed: {reason}"
        ) from None

    expected_inbound = fixture.get("Inbound")
    if isinstance(expected_inbound, dict):
        actual_response = normalize_test_response(
            response_payload,
            source_name)

        assert_expected_subset(
            actual_response,
            expected_inbound,
            "response")

    print(response_payload)
    return 0
