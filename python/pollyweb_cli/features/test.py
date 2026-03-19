"""Test fixture loading and validation for the `pw test` command."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import re
import socket
import time
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
from pollyweb_cli.tools.debug import parse_debug_payload
from pollyweb_cli.tools.transport import send_wallet_message


def describe_http_test_error(exc: urllib.error.HTTPError) -> str:
    """Build the user-facing HTTP failure message for `pw test`."""

    message = f"HTTP {exc.code} {exc.reason}."
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

PLACEHOLDER_PATTERN = re.compile(r"^\{BindOf\(([^)]+)\)\}$")
PUBLIC_KEY_PLACEHOLDER = "<PublicKey>"
UUID_WILDCARD = "<uuid>"
STRING_WILDCARD = "<str>"
TIMESTAMP_WILDCARD = "<timestamp>"
DEFAULT_TESTS_DIR = "pw-tests"

# ISO-8601 UTC timestamp ending in Z, matching the pollyweb Zulu timestamp format.
_Z_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$"
)


def format_test_success_message(
    fixture_name: str,
    *,
    total_seconds: float,
    network_seconds: float
) -> str:
    """Build the concise success line for one passing test fixture."""

    total_milliseconds = max(0, round(total_seconds * 1000))
    network_share = 0.0

    if total_seconds > 0:
        network_share = (network_seconds / total_seconds) * 100

    return (
        f"✅ Passed: {fixture_name} ({total_milliseconds} ms, "
        f"{network_share:.0f}% latency)"
    )


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

    # Some proxied domains return a plain JSON body inside the shared
    # `Proxy@Domain` envelope.  In that case, unwrap the nested response so
    # fixtures can assert against the actual service body instead of the
    # transport wrapper.
    if set(loaded.keys()) == {"Request", "Response"}:
        nested_response = loaded.get("Response")
        if (
            isinstance(nested_response, dict)
            and "Header" not in nested_response
            and "Body" not in nested_response
        ):
            loaded = dict(nested_response)

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

    def is_empty_value(value: Any) -> bool:
        """Return whether a fixture value should count as empty."""

        if value in ("", "''", None):
            return True

        if value == {}:
            return True

        return False

    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise UserFacingError(
                f"Expected {location} to be an object, but got {actual!r}."
            ) from None

        for key, expected_value in expected.items():
            # Treat empty expected scalar values as optional-presence checks.
            # A fixture can still assert an explicit empty value when the
            # response includes it, but omission is also accepted so callers
            # can express "blank or absent" fields such as Header.Algorithm.
            if key not in actual and is_empty_value(expected_value):
                continue

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

    # Allow fixtures to require "some non-empty string here" without pinning
    # the exact server-generated value.
    if expected == STRING_WILDCARD:
        if not isinstance(actual, str):
            raise UserFacingError(
                f"Expected {location} to be a string, but got {actual!r}."
            ) from None

        if not actual:
            raise UserFacingError(
                f"Expected {location} to be a non-empty string, but got {actual!r}."
            ) from None

        return

    # Allow fixtures to require "some valid Zulu timestamp here" without
    # pinning the exact server-generated value.  The accepted format mirrors
    # the pollyweb Msg.header.timestamp Zulu format exactly.
    if expected == TIMESTAMP_WILDCARD:
        if not isinstance(actual, str):
            raise UserFacingError(
                f"Expected {location} to be a timestamp string, but got {actual!r}."
            ) from None

        if not _Z_TIMESTAMP_RE.fullmatch(actual):
            raise UserFacingError(
                f"Expected {location} to be a Zulu timestamp "
                f"(e.g. 2024-01-02T03:04:05.678Z), but got {actual!r}."
            ) from None

        try:
            datetime.fromisoformat(actual.replace("Z", "+00:00"))
        except ValueError:
            raise UserFacingError(
                f"Expected {location} to be a valid Zulu timestamp, but got {actual!r}."
            ) from None

        return

    if is_empty_value(expected) and is_empty_value(actual):
        return

    if actual != expected:
        raise UserFacingError(
            f"Expected {location} to equal {expected!r}, but got {actual!r}."
        ) from None


def cmd_test(
    test_path: str | None,
    *,
    debug: bool,
    json_output: bool,
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
                json_output = json_output,
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
    json_output: bool,
    config_dir: Path,
    binds_path: Path,
    unsigned: bool,
    anonymous: bool,
    require_configured_keys,
    load_signing_key_pair
) -> None:
    """Send one wrapped test fixture and verify its expected inbound response."""

    started_at = time.perf_counter()
    timing: dict[str, float] = {}

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
            debug_json = json_output,
            from_value = request.get("From"),
            schema_value = request.get("Schema"),
            anonymous = anonymous,
            unsigned = unsigned,
            timing = timing,
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
            describe_http_test_error(exc)
        ) from None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, socket.gaierror):
            host = describe_message_network_error(str(request["To"]), exc.reason)
            raise UserFacingError(host) from None
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

    total_seconds = time.perf_counter() - started_at
    network_seconds = timing.get("network_seconds", 0.0)
    print(
        format_test_success_message(
            fixture_path.stem,
            total_seconds = total_seconds,
            network_seconds = network_seconds)
    )
