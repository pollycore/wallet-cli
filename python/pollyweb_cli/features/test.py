"""Test fixture loading and validation for the `pw test` command."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from concurrent.futures import as_completed
from dataclasses import dataclass, field
import json
from datetime import datetime
from itertools import count
from pathlib import Path
import re
import socket
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event, Lock, Thread, current_thread
import time
import urllib.error
from typing import Any
import uuid

import yaml
from rich.cells import cell_len
from rich.live import Live

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
from pollyweb_cli.tools.debug import (
    DEBUG_CONSOLE,
    parse_debug_payload,
)
from pollyweb_cli.tools.transport import send_wallet_message
from pollyweb_cli.tools.transport import rewrite_backend_validation_error
from pollyweb_cli.tools.transport import DEFAULT_SEND_TIMEOUT_SECONDS


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
            return (
                f"{message} "
                f"{rewrite_backend_validation_error(error_value)}"
            )

    return message


def is_timeout_reason(
    reason: object
) -> bool:
    """Return whether one transport failure reason represents a timeout."""

    if isinstance(reason, TimeoutError):
        return True

    if isinstance(reason, socket.timeout):
        return True

    if isinstance(reason, str):
        return "timed out" in reason.lower()

    return "timed out" in str(reason).lower()


def format_timeout_seconds(
    value: float
) -> str:
    """Render one timeout-related duration with one decimal place."""

    return f"{max(0.0, value):.1f}s"


def describe_test_timeout_error(
    domain: str,
    *,
    elapsed_seconds: float,
    client_timeout_seconds: float,
    wait_seconds: float
) -> str:
    """Build a user-facing timeout message for `pw test` transport failures."""

    timeout_summary = (
        f"Client timeout after {format_timeout_seconds(client_timeout_seconds)} "
        f"while waiting for a response from {domain}."
    )
    detail_parts = [
        f"Send elapsed: {format_timeout_seconds(elapsed_seconds)}.",
        "Server timing unavailable because no response was received.",
    ]

    if wait_seconds > 0:
        detail_parts.append(
            f"Fixture wait before send: {format_timeout_seconds(wait_seconds)}."
        )

    return f"{timeout_summary} {' '.join(detail_parts)}"

PLACEHOLDER_PATTERN = re.compile(r"^\{BindOf\(([^)]+)\)\}$")
PUBLIC_KEY_PLACEHOLDER = "<PublicKey>"
UUID_WILDCARD = "<uuid>"
STRING_WILDCARD = "<str>"
INTEGER_WILDCARD = "<int>"
TIMESTAMP_WILDCARD = "<timestamp>"
DEFAULT_TESTS_DIR = "pw-tests"
PARALLEL_FIXTURE_PREFIX_PATTERN = re.compile(r"^(\d+)-")
PARALLEL_STATUS_ROOT_LABEL = ""
PARALLEL_TEST_SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
ACTIVE_TEST_SPINNER_COUNT: ContextVar[int] = ContextVar(
    "active_test_spinner_count",
    default = 0,
)
ACTIVE_PARALLEL_TEST_STATUS_COUNT: ContextVar[int] = ContextVar(
    "active_parallel_test_status_count",
    default = 0,
)

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


def format_test_spinner_message(
    fixture_name: str
) -> str:
    """Build the per-fixture spinner label for `pw test` sends."""

    return f"Testing message: {fixture_name}"


def format_test_group_spinner_message(
    group_name: str
) -> str:
    """Build the shared spinner label for one parallel test group."""

    return f"Testing message group: {group_name}"


@dataclass
class _ParallelStatusNode:
    """Represent one branch in the hierarchical parallel test status view."""

    label: str
    children: dict[str, "_ParallelStatusNode"] = field(default_factory = dict)


class ParallelTestLiveDisplay:
    """Wrap a Rich live display with the status-like interface used in tests."""

    def __init__(
        self,
        message: str
    ):
        """Store the initial message and create the live renderer."""

        self.message = message
        self._live = Live(
            message,
            console = DEBUG_CONSOLE,
            auto_refresh = False,
            refresh_per_second = 12.5,
            transient = False,
        )

    def __enter__(self):
        """Start the live renderer and return this adapter."""

        self._live.__enter__()
        return self

    def update(
        self,
        message: str
    ) -> None:
        """Replace the live tree with one fresh rendered message."""

        self.message = message
        self._live.update(message, refresh = True)

    def __exit__(
        self,
        exc_type,
        exc,
        tb
    ) -> bool:
        """Stop the live renderer without suppressing exceptions."""

        return bool(self._live.__exit__(exc_type, exc, tb))


def normalize_parallel_test_status_message(
    message: str,
    previous_message: str | None
) -> str:
    """Pad status lines so later shorter renders fully overwrite earlier ones."""

    current_lines = message.splitlines() or [""]
    previous_lines = previous_message.splitlines() if previous_message else []
    total_lines = max(len(current_lines), len(previous_lines))
    normalized_lines: list[str] = []

    for index in range(total_lines):
        current_line = current_lines[index] if index < len(current_lines) else ""
        previous_line = previous_lines[index] if index < len(previous_lines) else ""
        target_width = max(cell_len(current_line), cell_len(previous_line))
        padding = max(0, target_width - cell_len(current_line))
        normalized_lines.append(f"{current_line}{' ' * padding}")

    return "\n".join(normalized_lines)


class ParallelTestStatusRenderer:
    """Maintain one shared hierarchical Rich status for active parallel work."""

    def __init__(self):
        """Initialize the renderer state."""

        self._lock = Lock()
        self._active_paths: dict[int, tuple[str, ...]] = {}
        self._resolved_paths: dict[int, tuple[str, ...]] = {}
        self._resolved_rendered_events: dict[int, Event] = {}
        self._token_counter = count(1)
        self._change_event = Event()
        self._render_started_event = Event()
        self._render_thread: Thread | None = None

    def push(
        self,
        path: tuple[str, ...]
    ) -> int:
        """Register one active hierarchical path and refresh the status."""

        previous_render_thread: Thread | None = None

        with self._lock:
            if not self._active_paths and not self._resolved_paths:
                previous_render_thread = self._render_thread
            token = next(self._token_counter)
            self._active_paths[token] = path
            if (
                self._render_thread is None
                or not self._render_thread.is_alive()
            ):
                self._render_started_event.clear()
                self._render_thread = Thread(
                    target = self._run_render_loop,
                    name = "pw-test-status",
                    daemon = True,
                )
                self._render_thread.start()
            self._change_event.set()

        if (
            previous_render_thread is not None
            and previous_render_thread.is_alive()
            and previous_render_thread is not current_thread()
        ):
            previous_render_thread.join(timeout = 1)

            with self._lock:
                if self._render_thread is previous_render_thread:
                    self._render_started_event.clear()
                    self._render_thread = Thread(
                        target = self._run_render_loop,
                        name = "pw-test-status",
                        daemon = True,
                    )
                    self._render_thread.start()
                    self._change_event.set()

        self._render_started_event.wait(timeout = 0.2)
        return token

    def pop(
        self,
        token: int
    ) -> None:
        """Remove one active hierarchical path and refresh the status."""

        render_thread: Thread | None = None
        rendered_event: Event | None = None

        with self._lock:
            self._active_paths.pop(token, None)
            rendered_event = self._resolved_rendered_events.get(token)
            if token not in self._resolved_paths:
                self._change_event.set()
            elif not self._active_paths:
                render_thread = self._render_thread

        if rendered_event is not None:
            rendered_event.wait(timeout = 1)

        with self._lock:
            self._resolved_paths.pop(token, None)
            self._resolved_rendered_events.pop(token, None)
            if not self._active_paths and not self._resolved_paths:
                render_thread = self._render_thread
            self._change_event.set()

        if (
            render_thread is not None
            and render_thread.is_alive()
            and render_thread is not current_thread()
        ):
            render_thread.join(timeout = 1)

            with self._lock:
                if render_thread is self._render_thread and not render_thread.is_alive():
                    self._render_thread = None

    def resolve(
        self,
        token: int,
        path: tuple[str, ...]
    ) -> None:
        """Replace one active path with its final rendered result label."""

        with self._lock:
            self._active_paths.pop(token, None)
            self._resolved_paths[token] = path
            self._resolved_rendered_events[token] = Event()
            self._change_event.set()

    def close(
        self,
        token: int
    ) -> None:
        """Retire one already-resolved path after its final snapshot is shown."""
        with self._lock:
            rendered_event = self._resolved_rendered_events.get(token)

        if rendered_event is not None:
            rendered_event.wait(timeout = 1)

        with self._lock:
            self._resolved_paths.pop(token, None)
            self._resolved_rendered_events.pop(token, None)
            render_thread = self._render_thread
            self._change_event.set()

        if (
            render_thread is not None
            and render_thread.is_alive()
            and render_thread is not current_thread()
        ):
            render_thread.join(timeout = 1)

    def _run_render_loop(self) -> None:
        """Render status updates from one dedicated thread."""

        status_context = None
        status_handle = None
        last_message: str | None = None
        spinner_frame_index = 0

        try:
            while True:
                with self._lock:
                    active_paths = dict(self._active_paths)
                    resolved_paths = dict(self._resolved_paths)

                if not active_paths and not resolved_paths:
                    break

                message = build_parallel_test_status_message(
                    build_parallel_test_render_paths(
                        active_paths,
                        resolved_paths,
                        spinner_frame = PARALLEL_TEST_SPINNER_FRAMES[
                            spinner_frame_index % len(PARALLEL_TEST_SPINNER_FRAMES)
                        ],
                    )
                )
                normalized_message = normalize_parallel_test_status_message(
                    message,
                    last_message,
                )
                if normalized_message != last_message:
                    if status_context is None:
                        status_context = open_parallel_test_status(normalized_message)
                        status_handle = status_context.__enter__()
                        self._render_started_event.set()
                    elif hasattr(status_handle, "update"):
                        status_handle.update(normalized_message)

                    last_message = normalized_message

                if resolved_paths:
                    with self._lock:
                        for token in resolved_paths:
                            rendered_event = self._resolved_rendered_events.get(token)
                            if rendered_event is not None:
                                rendered_event.set()

                if active_paths:
                    spinner_frame_index += 1

                self._change_event.wait(timeout = 0.05)
                self._change_event.clear()
        finally:
            if status_context is not None:
                status_context.__exit__(None, None, None)

            with self._lock:
                self._resolved_paths.clear()
                self._resolved_rendered_events.clear()
                if current_thread() is self._render_thread:
                    self._render_thread = None
            self._render_started_event.set()


PARALLEL_TEST_STATUS_RENDERER = ParallelTestStatusRenderer()


def reset_parallel_test_status_renderer() -> None:
    """Start one fresh shared renderer for each top-level `pw test` command."""

    global PARALLEL_TEST_STATUS_RENDERER
    PARALLEL_TEST_STATUS_RENDERER = ParallelTestStatusRenderer()


def open_parallel_test_status(
    message: str
) -> ParallelTestLiveDisplay:
    """Create the live grouped-status display for parallel `pw test` work."""

    return ParallelTestLiveDisplay(message)


def build_parallel_test_render_paths(
    active_paths: dict[int, tuple[str, ...]],
    resolved_paths: dict[int, tuple[str, ...]],
    *,
    spinner_frame: str = PARALLEL_TEST_SPINNER_FRAMES[0],
) -> list[tuple[str, ...]]:
    """Return renderer paths in stable token order across state transitions."""

    render_paths: list[tuple[str, ...]] = []
    for token in sorted(set(active_paths) | set(resolved_paths)):
        path = resolved_paths.get(token)
        if path is None:
            path = active_paths.get(token)
            if path is not None and path:
                last_label = path[-1]
                if not last_label or _is_group_label(last_label):
                    render_paths.append(path)
                    continue
                path = (
                    *path[:-1],
                    f"{spinner_frame} {format_test_spinner_message(last_label)}",
                )
        if path is not None:
            render_paths.append(path)
    return render_paths


def _is_group_label(label: str) -> bool:
    """Return whether one status label refers to a group rather than a fixture."""

    return (
        label == PARALLEL_STATUS_ROOT_LABEL
        or
        label.startswith("files ")
        or label.startswith("folders ")
        or label.startswith("✔️ Passed:")
    )


def build_parallel_test_status_message(
    active_paths: list[tuple[str, ...]]
) -> str:
    """Render the flat status text for active parallel test work."""

    root = _ParallelStatusNode(label = "Testing messages in parallel")

    for path in active_paths:
        node_stack: list[_ParallelStatusNode] = [root]
        last_unindented_depth = 0

        for raw_label in path:
            stripped_label = raw_label.lstrip(" ")
            indent_width = len(raw_label) - len(stripped_label)
            indent_levels = indent_width // 2

            if indent_levels > 0:
                depth = last_unindented_depth + indent_levels
            else:
                depth = len(node_stack)
                last_unindented_depth = depth

            while len(node_stack) > depth:
                node_stack.pop()

            parent = node_stack[-1]
            current = parent.children.setdefault(
                stripped_label,
                _ParallelStatusNode(label = stripped_label),
            )
            node_stack.append(current)

    lines: list[str] = []

    def append_children(
        node: _ParallelStatusNode,
    ) -> None:
        """Append all non-group labels from one node subtree."""

        for child in node.children.values():
            if not _is_group_label(child.label):
                lines.append(child.label)
            append_children(child)

    append_children(root)
    return "\n".join(lines)


@contextmanager
def test_parallel_status_scope(
    *labels: str
):
    """Register one shared parallel status path for the duration of a scope."""

    active_count = ACTIVE_PARALLEL_TEST_STATUS_COUNT.get()
    token = ACTIVE_PARALLEL_TEST_STATUS_COUNT.set(active_count + 1)
    status_token = PARALLEL_TEST_STATUS_RENDERER.push(tuple(labels))
    try:
        yield status_token
    finally:
        PARALLEL_TEST_STATUS_RENDERER.pop(status_token)
        ACTIVE_PARALLEL_TEST_STATUS_COUNT.reset(token)


@contextmanager
def test_parallel_status(
    *labels: str
):
    """Show one shared hierarchical status for active parallel test work."""

    with test_parallel_status_scope(*labels) as status_token:
        yield status_token


@contextmanager
def test_spinner_status(
    message: str
):
    """Show one test spinner unless another test spinner is already active."""

    active_spinner_count = ACTIVE_TEST_SPINNER_COUNT.get()
    if active_spinner_count > 0:
        with nullcontext():
            yield
        return

    spinner_token = ACTIVE_TEST_SPINNER_COUNT.set(active_spinner_count + 1)
    try:
        with DEBUG_CONSOLE.status(message):
            yield
    finally:
        ACTIVE_TEST_SPINNER_COUNT.reset(spinner_token)


def get_test_fixture_display_name(
    fixture_path: Path
) -> str:
    """Build the user-facing fixture name for concise test output."""

    current_dir = Path.cwd()
    tests_dir = current_dir / DEFAULT_TESTS_DIR

    try:
        relative_path = fixture_path.relative_to(tests_dir)
    except ValueError:
        relative_path = None

    if relative_path is not None:
        display_path = relative_path
    else:
        try:
            workspace_relative_path = fixture_path.relative_to(current_dir)
        except ValueError:
            display_path = Path(fixture_path.stem)
        else:
            if len(workspace_relative_path.parts) > 1:
                display_path = workspace_relative_path
            else:
                display_path = Path(fixture_path.stem)

    return display_path.with_suffix("").as_posix()


def extract_test_response_total_seconds(
    response_payload: str
) -> float | None:
    """Read the wrapped response total-duration hint from one sync payload."""

    try:
        loaded_payload = json.loads(response_payload)
    except json.JSONDecodeError:
        return None

    if not isinstance(loaded_payload, dict):
        return None

    wrapped_response = loaded_payload.get("Response")
    if not isinstance(wrapped_response, dict):
        return None

    response_metadata = wrapped_response.get("Meta")
    if not isinstance(response_metadata, dict):
        return None

    total_milliseconds = response_metadata.get("TotalMs")
    if isinstance(total_milliseconds, bool) or not isinstance(total_milliseconds, int):
        return None

    if total_milliseconds < 0:
        return None

    return total_milliseconds / 1000


def extract_test_total_seconds(
    response_payload: str,
    *,
    measured_total_seconds: float
) -> float:
    """Choose the best total duration hint for `pw test` success output."""

    total_seconds = measured_total_seconds
    response_total_seconds = extract_test_response_total_seconds(response_payload)
    if response_total_seconds is None:
        return total_seconds

    # Treat the wrapped sync metadata as a timing hint so the concise success
    # line can reflect server-reported end-to-end duration when it is available
    # without undercutting a larger locally measured wall-clock duration.
    return max(total_seconds, response_total_seconds)


def extract_test_latency_seconds(
    response_payload: str,
    *,
    total_seconds: float,
    network_seconds: float
) -> float:
    """Choose the transport-latency share shown in `pw test` success output."""

    response_total_seconds = extract_test_response_total_seconds(response_payload)

    if response_total_seconds is None:
        return network_seconds

    # When the response reports its own end-to-end execution time, treat that
    # server-side total as part of the round trip before calculating the
    # remaining transport share for the concise success line.
    return max(0.0, total_seconds - response_total_seconds)


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

    wait = loaded.get("Wait")
    if wait is not None:
        if isinstance(wait, bool) or not isinstance(wait, (int, float)):
            raise UserFacingError(
                f"Test file {path} must define `Wait` as a number when present."
            ) from None

        if wait < 0:
            raise UserFacingError(
                f"Test file {path} must define `Wait` as a non-negative number."
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


def extract_test_failure(
    payload: str,
    source_name: str
) -> str | None:
    """Return a user-facing server failure summary when one is present."""

    normalized = normalize_test_response(
        payload,
        source_name)
    candidates: list[dict[str, Any]] = []

    if isinstance(normalized, dict):
        candidates.append(normalized)

        meta = normalized.get("Meta")
        if isinstance(meta, dict):
            candidates.append(meta)

        wrapped_response = normalized.get("Response")
        if isinstance(wrapped_response, dict):
            candidates.append(wrapped_response)

            wrapped_meta = wrapped_response.get("Meta")
            if isinstance(wrapped_meta, dict):
                candidates.append(wrapped_meta)

    for candidate in candidates:
        code = candidate.get("Code")
        if isinstance(code, bool) or not isinstance(code, int):
            continue

        if code < 500:
            continue

        failure_parts = [f"Response returned Code {code}"]
        message = candidate.get("Message")
        if isinstance(message, str) and message.strip():
            failure_parts.append(message.strip())

        details = candidate.get("Details")
        if isinstance(details, list):
            detail_values = [
                str(item).strip()
                for item in details
                if str(item).strip()
            ]
            if detail_values:
                failure_parts.append(f"Details: {' | '.join(detail_values)}")

        return ". ".join(failure_parts)

    return None


def assert_expected_subset(
    actual: Any,
    expected: Any,
    location: str
) -> None:
    """Assert that a response contains the expected fixture subset."""

    def contains_array_template_placeholder(value: Any) -> bool:
        """Return whether a list item includes a repeatable wildcard template."""

        if isinstance(value, dict):
            return any(
                contains_array_template_placeholder(nested_value)
                for nested_value in value.values()
            )

        if isinstance(value, list):
            return any(
                contains_array_template_placeholder(item)
                for item in value
            )

        return value in {
            UUID_WILDCARD,
            STRING_WILDCARD,
            INTEGER_WILDCARD,
        }

    def match_expected_list(
        actual_list: list[Any],
        expected_list: list[Any],
        list_location: str
    ) -> None:
        """Assert that a response list matches fixed items and an optional template."""

        template_items = [
            (index, item)
            for index, item in enumerate(expected_list)
            if contains_array_template_placeholder(item)
        ]
        fixed_items = [
            (index, item)
            for index, item in enumerate(expected_list)
            if not contains_array_template_placeholder(item)
        ]

        if not template_items:
            if len(actual_list) != len(expected_list):
                raise UserFacingError(
                    f"Expected {list_location} to contain {len(expected_list)} items, "
                    f"but got {len(actual_list)}."
                ) from None

            for index, expected_item in enumerate(expected_list):
                try:
                    assert_expected_subset(
                        actual_list[index],
                        expected_item,
                        f"{list_location}[{index}]")
                except UserFacingError as exc:
                    item_found_elsewhere = False

                    for candidate_item in actual_list:
                        try:
                            assert_expected_subset(
                                candidate_item,
                                expected_item,
                                f"{list_location}[{index}]")
                        except UserFacingError:
                            continue

                        item_found_elsewhere = True
                        break

                    if not item_found_elsewhere:
                        raise UserFacingError(
                            f"Expected item {expected_item!r} was not found in {list_location}."
                        ) from None

                    raise exc
            return

        unmatched_actual_indexes = list(range(len(actual_list)))

        for expected_index, expected_item in fixed_items:
            matched_index: int | None = None

            for actual_index in unmatched_actual_indexes:
                try:
                    assert_expected_subset(
                        actual_list[actual_index],
                        expected_item,
                        f"{list_location}[{expected_index}]")
                except UserFacingError:
                    continue

                matched_index = actual_index
                break

            if matched_index is None:
                if not actual_list:
                    raise UserFacingError(
                        f"Expected {list_location}[{expected_index}] to exist in the response."
                    ) from None

                raise UserFacingError(
                    f"Expected item {expected_item!r} was not found in {list_location}."
                ) from None

            unmatched_actual_indexes.remove(matched_index)

        for actual_index in unmatched_actual_indexes:
            template_matched = False

            for expected_index, template_item in template_items:
                try:
                    assert_expected_subset(
                        actual_list[actual_index],
                        template_item,
                        f"{list_location}[{expected_index}]")
                except UserFacingError:
                    continue

                template_matched = True
                break

            if not template_matched:
                assert_expected_subset(
                    actual_list[actual_index],
                    template_items[0][1],
                    f"{list_location}[{template_items[0][0]}]")

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

    if isinstance(expected, list):
        if not isinstance(actual, list):
            raise UserFacingError(
                f"Expected {location} to be an array, but got {actual!r}."
            ) from None

        match_expected_list(actual, expected, location)
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

    # Allow fixtures to require "some integer here" without pinning the exact
    # server-generated numeric value.  Exclude booleans because Python treats
    # them as ints, but PollyWeb payloads should distinguish them clearly.
    if expected == INTEGER_WILDCARD:
        if isinstance(actual, bool) or not isinstance(actual, int):
            raise UserFacingError(
                f"Expected {location} to be an integer, but got {actual!r}."
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

    # Reset the shared parallel renderer per command so each `pw test` run
    # owns a fresh status thread and current console monkeypatches/TTY state.
    reset_parallel_test_status_renderer()

    test_target_path = resolve_test_target_path(test_path)

    run_test_target(
        test_target_path,
        debug = debug,
        json_output = json_output,
        config_dir = config_dir,
        binds_path = binds_path,
        unsigned = unsigned,
        anonymous = anonymous,
        require_configured_keys = require_configured_keys,
        load_signing_key_pair = load_signing_key_pair,
        emit_output_line = print)

    return 0


def run_test_target(
    test_target_path: Path,
    *,
    debug: bool,
    json_output: bool,
    config_dir: Path,
    binds_path: Path,
    unsigned: bool,
    anonymous: bool,
    require_configured_keys,
    load_signing_key_pair,
    emit_output_line = None,
    active_parallel_labels: tuple[str, ...] = (),
) -> list[str]:
    """Run one file or directory test target and return its output lines."""

    if not test_target_path.is_dir():
        fixture_name = get_test_fixture_display_name(test_target_path)
        try:
            output_line = run_message_test_fixture(
                test_target_path,
                fixture_name = fixture_name,
                debug = debug,
                json_output = json_output,
                config_dir = config_dir,
                binds_path = binds_path,
                unsigned = unsigned,
                anonymous = anonymous,
                require_configured_keys = require_configured_keys,
                load_signing_key_pair = load_signing_key_pair,
                active_parallel_labels = active_parallel_labels,
            )
            if emit_output_line is not None:
                if active_parallel_labels:
                    return [output_line]
                emit_output_line(output_line)
                return []
            return [output_line]
        except Exception as exc:
            if not getattr(exc, "parallel_failure_already_reported", False):
                print(f"❌ Failed: {fixture_name}")
            setattr(exc, "parallel_failure_display_name", fixture_name)
            setattr(
                exc,
                "parallel_failure_already_reported",
                active_parallel_labels or getattr(
                    exc,
                    "parallel_failure_already_reported",
                    False,
                ),
            )
            raise

    target_runs = collect_test_target_runs(test_target_path)
    output_lines: list[str] = []

    for target_group in group_parallel_test_targets(
        target_runs,
        debug = debug):
        if len(target_group) == 1:
            target_run = target_group[0]
            output_lines.extend(
                run_test_target(
                    target_run["path"],
                    debug = debug,
                    json_output = json_output,
                    config_dir = config_dir,
                    binds_path = binds_path,
                    unsigned = unsigned,
                    anonymous = anonymous,
                    require_configured_keys = require_configured_keys,
                    load_signing_key_pair = load_signing_key_pair,
                    emit_output_line = emit_output_line,
                    active_parallel_labels = active_parallel_labels,
                )
            )
            continue

        group_child_lines_by_name: dict[str, list[str]] = {}
        group_labels = (*active_parallel_labels, PARALLEL_STATUS_ROOT_LABEL)
        parallel_group_scope = test_parallel_status(
            *group_labels
        )
        if active_parallel_labels:
            parallel_group_scope = test_parallel_status_scope(
                *group_labels
            )
        group_summary_lines: list[str] = []

        with parallel_group_scope:
            with ThreadPoolExecutor(max_workers = len(target_group)) as executor:
                future_results: dict[Future[list[str]], dict[str, Path | str]] = {
                    executor.submit(
                        run_test_target,
                        target_run["path"],
                        debug = debug,
                        json_output = json_output,
                        config_dir = config_dir,
                        binds_path = binds_path,
                        unsigned = unsigned,
                        anonymous = anonymous,
                        require_configured_keys = require_configured_keys,
                        load_signing_key_pair = load_signing_key_pair,
                        emit_output_line = emit_output_line,
                        active_parallel_labels = group_labels,
                    ): target_run
                    for target_run in target_group
                }

                for future in as_completed(future_results):
                    target_run = future_results[future]
                    try:
                        future_output_lines = future.result()
                    except Exception as exc:
                        failure_name = getattr(
                            exc,
                            "parallel_failure_display_name",
                            target_run["name"],
                        )
                        if not getattr(
                            exc,
                            "parallel_failure_already_reported",
                            False,
                        ):
                            print(f"❌ Failed: {failure_name}")
                        raise

                    group_child_lines_by_name[str(target_run["name"])] = future_output_lines

            group_child_lines: list[str] = []
            for target_run in target_group:
                group_child_lines.extend(
                    group_child_lines_by_name.get(
                        str(target_run["name"]),
                        [],
                    )
                )

            group_summary_lines = list(group_child_lines)

        if emit_output_line is not None:
            if active_parallel_labels:
                output_lines.extend(group_summary_lines)
            continue

        output_lines.extend(group_summary_lines)

    return output_lines


def collect_test_target_runs(
    target_dir: Path
) -> list[dict[str, Path | str]]:
    """Collect one directory's immediate runnable test targets."""

    target_runs: list[dict[str, Path | str]] = []

    for child_path in sorted(target_dir.iterdir()):
        if child_path.is_file() and child_path.suffix == ".yaml":
            target_runs.append(
                {
                    "path": child_path,
                    "name": get_test_fixture_display_name(child_path),
                }
            )
            continue

        if child_path.is_dir() and directory_contains_yaml_fixtures(child_path):
            target_runs.append(
                {
                    "path": child_path,
                    "name": get_test_fixture_display_name(child_path),
                }
            )

    if target_runs:
        return target_runs

    raise UserFacingError(
        f"No YAML test fixtures were found in {target_dir}."
    ) from None


def directory_contains_yaml_fixtures(
    target_dir: Path
) -> bool:
    """Return whether one directory contains any YAML fixtures recursively."""

    return any(target_dir.rglob("*.yaml"))


def resolve_test_target_path(
    test_path: str | None
) -> Path:
    """Resolve the explicit or default `pw test` target path."""

    if test_path is not None:
        fixture_path = Path(test_path)
        if fixture_path.exists():
            return fixture_path

        if fixture_path.suffix == "":
            fixture_yaml_path = fixture_path.with_suffix(".yaml")
            if fixture_yaml_path.exists():
                return fixture_yaml_path

        fallback_fixture_path = Path.cwd() / DEFAULT_TESTS_DIR / test_path
        if fallback_fixture_path.exists():
            return fallback_fixture_path

        if fallback_fixture_path.suffix == "":
            fallback_fixture_yaml_path = fallback_fixture_path.with_suffix(".yaml")
            if fallback_fixture_yaml_path.exists():
                return fallback_fixture_yaml_path

        if fallback_fixture_path.is_dir():
            return fallback_fixture_path

        return fixture_path

    tests_dir = Path.cwd() / DEFAULT_TESTS_DIR
    if not tests_dir.exists():
        raise UserFacingError(
            f"No test path was provided and {tests_dir} does not exist."
        ) from None

    if not tests_dir.is_dir():
        raise UserFacingError(
            f"No test path was provided and {tests_dir} is not a directory."
        ) from None

    return tests_dir


def group_parallel_test_targets(
    target_runs: list[dict[str, Path | str]],
    *,
    debug: bool
) -> list[list[dict[str, Path | str]]]:
    """Group sibling test targets that can share one parallel execution wave."""

    if debug:
        return [[target_run] for target_run in target_runs]

    grouped_runs: list[list[dict[str, Path | str]]] = []
    current_group: list[dict[str, Path | str]] = []
    current_parent: Path | None = None
    current_prefix: str | None = None

    for target_run in target_runs:
        target_path = target_run["path"]
        assert isinstance(target_path, Path)
        match = PARALLEL_FIXTURE_PREFIX_PATTERN.match(target_path.name)
        prefix = match.group(1) if match is not None else None

        if prefix is None:
            if current_group:
                grouped_runs.append(current_group)
                current_group = []
                current_parent = None
                current_prefix = None

            grouped_runs.append([target_run])
            continue

        if (
            current_group
            and target_path.parent == current_parent
            and prefix == current_prefix
        ):
            current_group.append(target_run)
            continue

        if current_group:
            grouped_runs.append(current_group)

        current_group = [target_run]
        current_parent = target_path.parent
        current_prefix = prefix

    if current_group:
        grouped_runs.append(current_group)

    return grouped_runs


def get_parallel_test_group_name(
    target_group: list[dict[str, Path | str]]
) -> str:
    """Return the shared user-facing label for one parallel target group."""

    first_target_name = str(target_group[0]["name"])
    first_target_path = Path(first_target_name)
    match = PARALLEL_FIXTURE_PREFIX_PATTERN.match(first_target_path.name)
    if match is None:
        return first_target_name

    grouped_name = Path(f"{match.group(1)}-*")
    if len(first_target_path.parts) > 1:
        grouped_name = Path(*first_target_path.parts[:-1]) / grouped_name

    return grouped_name.as_posix()


def get_parallel_test_spinner_group_name(
    target_group: list[dict[str, Path | str]]
) -> str:
    """Return the user-facing label shown for one active parallel group."""

    target_paths = [
        target_run["path"]
        for target_run in target_group
        if isinstance(target_run.get("path"), Path)
    ]
    group_name = get_parallel_test_group_name(target_group)

    if target_paths and all(target_path.is_dir() for target_path in target_paths):
        return f"folders {group_name}"

    return f"files {group_name}"


def get_test_fixture_paths(
    test_path: str | None
) -> list[Path]:
    """Resolve explicit or default `pw test` fixture paths."""

    test_target_path = resolve_test_target_path(test_path)
    if not test_target_path.is_dir():
        return [test_target_path]

    return sorted(test_target_path.rglob("*.yaml"))


def run_message_test_fixture(
    fixture_path: Path,
    *,
    fixture_name: str,
    debug: bool,
    json_output: bool,
    config_dir: Path,
    binds_path: Path,
    unsigned: bool,
    anonymous: bool,
    require_configured_keys,
    load_signing_key_pair,
    active_parallel_labels: tuple[str, ...] = (),
) -> str:
    """Send one wrapped test fixture and verify its expected inbound response."""

    started_at = time.perf_counter()
    timing: dict[str, float] = {}
    parallel_status_token: int | None = None
    parallel_status_scope = nullcontext()

    try:
        require_configured_keys()
        key_pair = load_signing_key_pair()
        fixture = load_message_test_fixture(
            fixture_path,
            binds_path,
            config_dir / "public.pem")
        wait_seconds = float(fixture.get("Wait", 0))

        request, _ = parse_message_request(
            [json.dumps(fixture["Outbound"])])

        spinner_context = test_spinner_status(
            format_test_spinner_message(fixture_name)
        )
        if active_parallel_labels:
            parallel_status_scope = test_parallel_status_scope(
                *active_parallel_labels,
                fixture_name,
            )
            spinner_context = nullcontext()

        with parallel_status_scope as parallel_status_token:
            with spinner_context:
                # Keep the fixture spinner visible during any configured delay so
                # users can see progress immediately, then send after the pause.
                if wait_seconds > 0:
                    time.sleep(wait_seconds)

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
        if parallel_status_token is not None:
            PARALLEL_TEST_STATUS_RENDERER.resolve(
                parallel_status_token,
                (*active_parallel_labels, f"❌ Failed: {fixture_name}"),
            )
        if fixture_path.suffix in {".yaml", ".yml", ".json"}:
            raise UserFacingError(
                f"Test file not found: {fixture_path}"
            ) from None

        if not fixture_path.exists():
            raise UserFacingError(
                f"Test file not found: {fixture_path}"
            ) from None

        raise UserFacingError(
            f"Missing PollyWeb keys in {config_dir}. Run `pw config` first."
        ) from None
    except urllib.error.HTTPError as exc:
        if parallel_status_token is not None:
            PARALLEL_TEST_STATUS_RENDERER.resolve(
                parallel_status_token,
                (*active_parallel_labels, f"❌ Failed: {fixture_name}"),
            )
        error = UserFacingError(
            describe_http_test_error(exc)
        )
        if parallel_status_token is not None:
            setattr(error, "parallel_failure_already_reported", True)
        raise error from None
    except urllib.error.URLError as exc:
        if parallel_status_token is not None:
            PARALLEL_TEST_STATUS_RENDERER.resolve(
                parallel_status_token,
                (*active_parallel_labels, f"❌ Failed: {fixture_name}"),
            )
        elapsed_seconds = timing.get(
            "network_seconds",
            max(0.0, time.perf_counter() - started_at - wait_seconds),
        )
        if is_timeout_reason(exc.reason):
            reason = describe_test_timeout_error(
                str(request["To"]),
                elapsed_seconds = elapsed_seconds,
                client_timeout_seconds = float(
                    timing.get(
                        "client_timeout_seconds",
                        DEFAULT_SEND_TIMEOUT_SECONDS,
                    )
                ),
                wait_seconds = wait_seconds,
            )
        else:
            reason = describe_message_network_error(
                str(request["To"]),
                exc.reason)
        error = UserFacingError(reason)
        if parallel_status_token is not None:
            setattr(error, "parallel_failure_already_reported", True)
        raise error from None
    except OSError as exc:
        if parallel_status_token is not None:
            PARALLEL_TEST_STATUS_RENDERER.resolve(
                parallel_status_token,
                (*active_parallel_labels, f"❌ Failed: {fixture_name}"),
            )
        elapsed_seconds = timing.get(
            "network_seconds",
            max(0.0, time.perf_counter() - started_at - wait_seconds),
        )
        if is_timeout_reason(exc):
            reason = describe_test_timeout_error(
                str(request["To"]),
                elapsed_seconds = elapsed_seconds,
                client_timeout_seconds = float(
                    timing.get(
                        "client_timeout_seconds",
                        DEFAULT_SEND_TIMEOUT_SECONDS,
                    )
                ),
                wait_seconds = wait_seconds,
            )
        else:
            reason = describe_message_network_error(
                str(request["To"]),
                exc)
        error = UserFacingError(reason)
        if parallel_status_token is not None:
            setattr(error, "parallel_failure_already_reported", True)
        raise error from None

    try:
        actual_response = normalize_test_response(
            response_payload,
            fixture_name)

        failure_message = extract_test_failure(
            response_payload,
            fixture_name)
        if failure_message is not None:
            raise UserFacingError(
                failure_message
            ) from None

        expected_inbound = fixture.get("Inbound")
        if isinstance(expected_inbound, dict):

            assert_expected_subset(
                actual_response,
                expected_inbound,
                "response")

        total_seconds = time.perf_counter() - started_at
        total_seconds = extract_test_total_seconds(
            response_payload,
            measured_total_seconds = total_seconds)
        network_seconds = extract_test_latency_seconds(
            response_payload,
            total_seconds = total_seconds,
            network_seconds = timing.get("network_seconds", 0.0))
        output_line = format_test_success_message(
            fixture_name,
            total_seconds = total_seconds,
            network_seconds = network_seconds)
        if parallel_status_token is not None:
            PARALLEL_TEST_STATUS_RENDERER.resolve(
                parallel_status_token,
                (*active_parallel_labels, output_line),
            )
            parallel_status_token = None
        return output_line
    except Exception as exc:
        if parallel_status_token is not None:
            PARALLEL_TEST_STATUS_RENDERER.resolve(
                parallel_status_token,
                (*active_parallel_labels, f"❌ Failed: {fixture_name}"),
            )
            parallel_status_token = None
            setattr(exc, "parallel_failure_already_reported", True)
        raise
