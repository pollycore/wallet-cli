"""Test fixture loading and validation for the `pw test` command."""

from __future__ import annotations

import json
from pathlib import Path
import re
import socket
import urllib.error
from typing import Any
import uuid

import yaml

from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.features.bind import (
    get_first_bind_for_domain,
    load_binds,
    serialize_public_key_value,
)
from pollyweb_cli.features.msg import (
    describe_message_network_error,
    parse_message_request,
)
from pollyweb_cli.tools.transport import send_wallet_message

PLACEHOLDER_PATTERN = re.compile(r"^\{BindOf\(([^)]+)\)\}$")
PUBLIC_KEY_PLACEHOLDER = "<PublicKey>"
UUID_WILDCARD = "<uuid>"
DEFAULT_TESTS_DIR = "pw-tests"


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


def resolve_public_key_placeholder(
    value: str,
    public_key_path: Path
) -> str:
    """Resolve the `"<PublicKey>"` token from the configured wallet key."""

    if value != PUBLIC_KEY_PLACEHOLDER:
        return value

    try:
        public_key_pem = public_key_path.read_text(encoding = "utf-8")
    except FileNotFoundError:
        raise UserFacingError(
            f"Missing PollyWeb public key in {public_key_path}. "
            "Run `pw config` first."
        ) from None

    return serialize_public_key_value(public_key_pem)


def resolve_fixture_placeholders(
    value: Any,
    *,
    binds_path: Path,
    public_key_path: Path
) -> Any:
    """Recursively replace supported fixture placeholders before sending."""

    if isinstance(value, dict):
        return {
            key: resolve_fixture_placeholders(
                nested_value,
                binds_path = binds_path,
                public_key_path = public_key_path)
            for key, nested_value in value.items()
        }

    if isinstance(value, list):
        return [
            resolve_fixture_placeholders(
                item,
                binds_path = binds_path,
                public_key_path = public_key_path)
            for item in value
        ]

    if isinstance(value, str):
        resolved_value = resolve_bind_placeholder(value, binds_path)
        return resolve_public_key_placeholder(
            resolved_value,
            public_key_path)

    return value


def load_message_test_fixture(
    path: Path,
    binds_path: Path,
    public_key_path: Path
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

    return resolve_fixture_placeholders(
        loaded,
        binds_path = binds_path,
        public_key_path = public_key_path)


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

    # Allow fixtures to require "some valid UUID here" without pinning an
    # exact bind or correlation value.
    if expected == UUID_WILDCARD:
        if not isinstance(actual, str):
            raise UserFacingError(
                f"Expected {location} to be a UUID string, but got {actual!r}."
            ) from None

        try:
            uuid.UUID(actual)
        except (AttributeError, TypeError, ValueError):
            raise UserFacingError(
                f"Expected {location} to be a valid UUID, but got {actual!r}."
            ) from None

        return

    if actual != expected:
        raise UserFacingError(
            f"Expected {location} to equal {expected!r}, but got {actual!r}."
        ) from None


def cmd_test(
    test_path: str | None,
    *,
    debug: bool,
    config_dir: Path,
    binds_path: Path,
    unsigned: bool,
    anonymous: bool,
    require_configured_keys,
    load_signing_key_pair
) -> int:
    """Send one or more wrapped test fixtures and verify expected responses."""

    fixture_paths = get_test_fixture_paths(test_path)

    for fixture_path in fixture_paths:
        try:
            run_message_test_fixture(
                fixture_path,
                debug = debug,
                config_dir = config_dir,
                binds_path = binds_path,
                unsigned = unsigned,
                anonymous = anonymous,
                require_configured_keys = require_configured_keys,
                load_signing_key_pair = load_signing_key_pair)
        except Exception:
            print(f"❌ Failed: {fixture_path.stem}")
            raise

    return 0


def get_test_fixture_paths(
    test_path: str | None
) -> list[Path]:
    """Resolve explicit or default `pw test` fixture paths."""

    if test_path is not None:
        return [Path(test_path)]

    tests_dir = Path.cwd() / DEFAULT_TESTS_DIR
    if not tests_dir.exists():
        raise UserFacingError(
            f"No test path was provided and {tests_dir} does not exist."
        ) from None

    if not tests_dir.is_dir():
        raise UserFacingError(
            f"No test path was provided and {tests_dir} is not a directory."
        ) from None

    fixture_paths = sorted(tests_dir.glob("*.yaml"))
    if not fixture_paths:
        raise UserFacingError(
            f"No YAML test fixtures were found in {tests_dir}."
        ) from None

    return fixture_paths


def run_message_test_fixture(
    fixture_path: Path,
    *,
    debug: bool,
    config_dir: Path,
    binds_path: Path,
    unsigned: bool,
    anonymous: bool,
    require_configured_keys,
    load_signing_key_pair
) -> None:
    """Send one wrapped test fixture and verify its expected inbound response."""

    try:
        require_configured_keys()
        key_pair = load_signing_key_pair()
        fixture = load_message_test_fixture(
            fixture_path,
            binds_path,
            config_dir / "public.pem")

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
            anonymous = anonymous,
            unsigned = unsigned,
        )
    except FileNotFoundError:
        if fixture_path.suffix in {".yaml", ".yml", ".json"}:
            raise UserFacingError(
                f"Test file not found: {fixture_path}"
            ) from None
        raise UserFacingError(
            f"Missing PollyWeb keys in {config_dir}. Run `pw config` first."
        ) from None
    except urllib.error.HTTPError as exc:
        raise UserFacingError(
            f"HTTP {exc.code} {exc.reason}."
        ) from None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, socket.gaierror):
            raise UserFacingError("HTTP 502 Bad Gateway.") from None
        reason = describe_message_network_error(
            str(request["To"]),
            exc.reason)
        raise UserFacingError(reason) from None

    expected_inbound = fixture.get("Inbound")
    if isinstance(expected_inbound, dict):
        actual_response = normalize_test_response(
            response_payload,
            fixture_path.stem)

        assert_expected_subset(
            actual_response,
            expected_inbound,
            "response")

    print(f"✅ Passed: {fixture_path.stem}")
