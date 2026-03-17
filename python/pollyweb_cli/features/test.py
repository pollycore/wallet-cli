"""Test fixture loading and validation for the `pw test` command."""

from __future__ import annotations

import json
from pathlib import Path
import re
import socket
import urllib.error
from typing import Any

import yaml

from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.features.bind import (
    get_first_bind_for_domain,
    load_binds,
)
from pollyweb_cli.features.msg import (
    describe_message_network_error,
    parse_message_request,
)
from pollyweb_cli.tools.transport import send_wallet_message

PLACEHOLDER_PATTERN = re.compile(r"^\{BindOf\(([^)]+)\)\}$")


def resolve_bind_placeholder(
    value: str,
    binds_path: Path
) -> str:
    """Resolve one `{BindOf(domain)}` token from the stored binds file."""

    match = PLACEHOLDER_PATTERN.fullmatch(value.strip())
    if match is None:
        return value

    requested_domain = match.group(1).strip()
    if not requested_domain:
        raise UserFacingError(
            "Bind placeholder must include a non-empty domain."
        ) from None

    bind_value = get_first_bind_for_domain(
        requested_domain,
        load_binds(binds_path))
    if bind_value is None:
        raise UserFacingError(
            f"No bind stored for {requested_domain}. "
            f"Run `pw bind {requested_domain}` first."
        ) from None

    return bind_value


def resolve_fixture_bind_placeholders(
    value: Any,
    binds_path: Path
) -> Any:
    """Recursively replace supported bind placeholders inside a fixture."""

    if isinstance(value, dict):
        return {
            key: resolve_fixture_bind_placeholders(
                nested_value,
                binds_path)
            for key, nested_value in value.items()
        }

    if isinstance(value, list):
        return [
            resolve_fixture_bind_placeholders(
                item,
                binds_path)
            for item in value
        ]

    if isinstance(value, str):
        return resolve_bind_placeholder(value, binds_path)

    return value


def load_message_test_fixture(
    path: Path,
    binds_path: Path
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

    return resolve_fixture_bind_placeholders(loaded, binds_path)


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
    binds_path: Path,
    require_configured_keys,
    load_signing_key_pair
) -> int:
    """Send one wrapped test fixture and verify its expected inbound response."""

    source_name = f"test file {test_path}"

    try:
        require_configured_keys()
        key_pair = load_signing_key_pair()
        fixture_path = Path(test_path)
        fixture = load_message_test_fixture(
            fixture_path,
            binds_path)

        request, _ = parse_message_request(
            [json.dumps(fixture["Outbound"])])

        response_payload, _, _ = send_wallet_message(
            domain = str(request["To"]),
            subject = str(request["Subject"]),
            body = dict(request["Body"]),
            key_pair = key_pair,
            debug = debug,
            from_value = request.get("From"),
            schema_value = request.get("Schema"),
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
