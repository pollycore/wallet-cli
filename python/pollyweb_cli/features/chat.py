"""Interactive AppSync Events chat helpers for the CLI."""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from queue import Empty, Queue
import secrets
import sys
import threading
from typing import Final

from pollyweb import KeyPair, Msg, Wallet, normalize_domain_name
from rich.box import ROUNDED
from rich.panel import Panel
from rich.text import Text
import yaml
from websocket import WebSocket
from websocket import WebSocketConnectionClosedException
from websocket import WebSocketTimeoutException
from websocket import create_connection

from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.features.config import load_notifier_domain
from pollyweb_cli.tools.debug import print_debug_payload

try:
    from textual import events
    from textual.app import App, ComposeResult
    from textual.containers import Vertical
    from textual.widgets import Input, RichLog, Static
except ImportError:  # pragma: no cover - dependency is expected in runtime envs
    events = None
    App = None
    ComposeResult = object
    Vertical = None
    Input = None
    RichLog = None
    Static = None


DEFAULT_CHANNEL_NAMESPACE = "default"
CONNECT_SUBJECT = "Connect@Notifier"
TEXTUAL_AVAILABLE = App is not None
CHAT_POLL_SECONDS: Final[float] = 0.1


@dataclass(frozen = True)
class _ChatLine:
    """One line rendered in the interactive chat transcript."""

    text: str
    style: str = "white"


class AppSyncConnection:
    """Wrap a websocket connection to the notifier AppSync Events API."""

    def __init__(
        self,
        notifier_domain: str,
        wallet_id: str,
        auth_token: str,
        websocket_factory = create_connection
    ) -> None:
        """Initialize the connection dependencies for a notifier chat session."""

        # Keep the raw notifier domain so the CLI can print it in status messages.
        self.notifier_domain = notifier_domain

        # Reuse the wallet identifier as the subscription channel suffix.
        self.wallet_id = wallet_id

        # Reuse the signed wallet token for both connect and subscribe auth.
        self.auth_token = auth_token

        # Allow tests to replace the websocket creation logic with a stub.
        self.websocket_factory = websocket_factory

        # Track the underlying websocket so shutdown can unsubscribe cleanly.
        self.websocket: WebSocket | None = None

        # Reuse the generated subscribe ID during unsubscribe.
        self.subscription_id = secrets.token_hex(8)

        # Keep a distinct publish ID so publish acknowledgements can be matched.
        self.publish_id = secrets.token_hex(8)

        # Cache the current subscription channel string.
        self.channel = build_wallet_channel(wallet_id)

    def connect(self) -> None:
        """Open the websocket, then finish the AppSync Events handshake."""

        protocol_headers = [
            "aws-appsync-event-ws",
            f"header-{_encode_header_payload(build_websocket_headers(self.notifier_domain, self.auth_token))}",
        ]
        websocket_url = build_websocket_url(self.notifier_domain)

        # Open the websocket with the encoded authorization subprotocol payload.
        self.websocket = self.websocket_factory(
            websocket_url,
            subprotocols = protocol_headers)

        # Start the AppSync session before sending any subscribe or publish frames.
        self._send_json({"type": "connection_init"})
        response = self._recv_json()
        if response.get("type") != "connection_ack":
            raise UserFacingError(
                f"Chat connection failed: expected connection_ack, received {response}."
            )

    def subscribe(self) -> None:
        """Subscribe the current websocket to the wallet channel."""

        self._send_json(
            {
                "id": self.subscription_id,
                "type": "subscribe",
                "channel": self.channel,
                "authorization": build_subscribe_headers(
                    self.notifier_domain,
                    self.auth_token),
            },
        )

        # Wait for the explicit subscribe success frame before listening for data.
        while True:
            response = self._recv_json()
            response_type = response.get("type")
            if response_type == "subscribe_success":
                return
            if response_type in {"ka", "keepalive"}:
                continue
            raise UserFacingError(
                f"Chat subscription failed: expected subscribe_success, received {response}."
            )

    def publish(self, event: object) -> None:
        """Publish one JSON event to the current wallet channel."""

        payload = json.dumps(event, separators = (",", ":"))
        self._send_json(
            {
                "id": self.publish_id,
                "type": "publish",
                "channel": self.channel,
                "events": [payload],
                "authorization": build_subscribe_headers(
                    self.notifier_domain,
                    self.auth_token),
            },
        )

        # Wait for the explicit publish success frame before accepting more input.
        while True:
            response = self._recv_json()
            response_type = response.get("type")
            if response_type == "publish_success":
                return
            if response_type in {"ka", "keepalive"}:
                continue
            raise UserFacingError(
                f"Chat publish failed: expected publish_success, received {response}."
            )

    def listen_forever(self) -> None:
        """Print chat events until the user interrupts the process."""

        while True:
            message = self.receive_event()
            if message is None:
                continue

            should_stop, output_lines = _render_event_lines(message)
            for line in output_lines:
                print(line)

            if should_stop:
                return

    def receive_event(self) -> dict[str, object] | None:
        """Receive one meaningful websocket message from the chat stream."""

        while True:
            try:
                message = self._recv_json()
            except KeyboardInterrupt:
                raise
            except WebSocketConnectionClosedException as exc:
                raise UserFacingError("Chat connection closed unexpectedly.") from exc
            except WebSocketTimeoutException:
                return None

            message_type = message.get("type")
            if message_type in {"ka", "keepalive"}:
                return None
            if message_type == "data":
                return message
            if message_type == "error":
                raise UserFacingError(f"Chat stream returned an error: {message}")

    def set_timeout(
        self,
        timeout_seconds: float | None
    ) -> None:
        """Set the websocket timeout when the underlying client supports it."""

        if self.websocket is None:
            return

        settimeout = getattr(self.websocket, "settimeout", None)
        if callable(settimeout):
            settimeout(timeout_seconds)

    def close(self) -> None:
        """Unsubscribe and close the websocket when the session ends."""

        if self.websocket is None:
            return

        try:
            self._send_json(
                {
                    "id": self.subscription_id,
                    "type": "unsubscribe",
                }
            )
        except Exception:
            pass

        try:
            self.websocket.close()
        finally:
            self.websocket = None

    def _send_json(self, payload: dict[str, object]) -> None:
        """Serialize and send a websocket frame."""

        if self.websocket is None:
            raise UserFacingError("Chat connection is not open.")
        self.websocket.send(json.dumps(payload, separators = (",", ":")))

    def _recv_json(self) -> dict[str, object]:
        """Receive and decode a websocket frame into a JSON object."""

        if self.websocket is None:
            raise UserFacingError("Chat connection is not open.")

        payload = self.websocket.recv()
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        message = json.loads(payload)
        if not isinstance(message, dict):
            raise UserFacingError("Chat websocket returned a non-object message.")
        return message


def build_events_domain(notifier_domain: str) -> str:
    """Translate a notifier domain into its AppSync Events domain."""

    normalized_domain = normalize_domain_name(notifier_domain)
    return f"events.{normalized_domain}"


def build_websocket_url(notifier_domain: str) -> str:
    """Build the websocket endpoint URL for a notifier."""

    return f"wss://{build_events_domain(notifier_domain)}/event/realtime"


def build_wallet_channel(wallet_id: str) -> str:
    """Build the AppSync Events channel used for one wallet."""

    return f"/{DEFAULT_CHANNEL_NAMESPACE}/{wallet_id}"


def build_websocket_headers(
    notifier_domain: str,
    auth_token: str
) -> dict[str, str]:
    """Build the websocket connect headers for the Lambda authorizer."""

    return {
        "host": build_events_domain(notifier_domain),
        "Authorization": auth_token,
    }


def build_subscribe_headers(
    notifier_domain: str,
    auth_token: str
) -> dict[str, str]:
    """Build the subscribe authorization headers for the Lambda authorizer."""

    return build_websocket_headers(
        notifier_domain,
        auth_token)


def _encode_header_payload(headers: dict[str, str]) -> str:
    """Encode the auth headers using URL-safe base64 without padding."""

    payload = json.dumps(headers, separators = (",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _is_exit_payload(payload: object) -> bool:
    """Return whether the payload requests the listener to stop."""

    if payload == "EXIT":
        return True

    if isinstance(payload, dict):
        message = payload.get("message")
        if message == "EXIT":
            return True

    return False


def _render_payload_line(payload: object) -> str:
    """Render one payload object into the plain CLI transcript format."""

    if isinstance(payload, str):
        return payload

    return json.dumps(payload, sort_keys = True)


def _render_event_lines(message: dict[str, object]) -> tuple[bool, list[str]]:
    """Return plain output lines for one incoming AppSync message."""

    output_lines: list[str] = []
    event_list = message.get("event")
    if isinstance(event_list, list):
        for event in event_list:
            if _is_exit_payload(event):
                output_lines.append("Received EXIT. Stopping chat listener.")
                return True, output_lines

            output_lines.append(_render_payload_line(event))

        return False, output_lines

    payload = message.get("payload")
    if payload is not None:
        if _is_exit_payload(payload):
            return True, ["Received EXIT. Stopping chat listener."]

        return False, [_render_payload_line(payload)]

    return False, [json.dumps(message, sort_keys = True)]


def _print_event_payload(message: dict[str, object]) -> bool:
    """Render one incoming AppSync event payload and report whether to stop."""

    should_stop, output_lines = _render_event_lines(message)
    for line in output_lines:
        print(line)
    return should_stop


def load_wallet_id(
    config_path: Path
) -> str:
    """Read the configured wallet identifier from the wallet config."""

    if not config_path.exists():
        raise UserFacingError("Missing wallet configuration. Run `pw onboard` first.")

    config_payload = yaml.safe_load(config_path.read_text(encoding = "utf-8")) or {}
    if not isinstance(config_payload, dict):
        raise UserFacingError("Wallet configuration is invalid.")

    wallet_id = config_payload.get("Wallet")
    if not isinstance(wallet_id, str) or not wallet_id.strip():
        raise UserFacingError(
            "Missing Wallet in ~/.pollyweb/config.yaml. Run `pw onboard` again first."
        )

    return wallet_id.strip()


def build_auth_token(
    key_pair: KeyPair,
    notifier_domain: str,
    wallet_id: str,
    *,
    unsigned: bool = False
) -> str:
    """Build a signed wallet auth token for notifier chat connections."""

    normalized_domain = normalize_domain_name(notifier_domain)
    message = Msg(
        To = normalized_domain,
        From = "Anonymous",
        Subject = CONNECT_SUBJECT,
        Body = {"Wallet": wallet_id},
    )

    # Use the published wallet signing flow for non-anonymous sessions.
    if not unsigned and wallet_id != "Anonymous":
        message = Wallet(
            KeyPair = key_pair,
            ID = wallet_id,
        ).sign(message)

    payload = json.dumps(
        message.to_dict(),
        separators = (",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _format_chat_timestamp(
    current_time: datetime | None = None
) -> str:
    """Format one local transcript timestamp for the interactive chat view."""

    timestamp = datetime.now() if current_time is None else current_time
    return timestamp.strftime("%H:%M:%S")


def _chat_line_from_payload(
    payload: object,
    *,
    direction: str,
    current_time: datetime | None = None
) -> _ChatLine:
    """Build one timestamped transcript line for a sent or received payload."""

    timestamp = _format_chat_timestamp(current_time)
    if direction == "outbound":
        prefix = "You"
        style = "bold #d7875f"
    elif direction == "status":
        prefix = "Status"
        style = "#8b949e"
    else:
        prefix = "Remote"
        style = "bold #3b82f6"

    if direction == "status":
        body = str(payload)
    else:
        body = _render_payload_line(payload)

    return _ChatLine(
        text = f"[{timestamp}] {prefix}: {body}",
        style = style,
    )


def _chat_lines_from_event(
    message: dict[str, object],
    *,
    current_time: datetime | None = None
) -> tuple[bool, list[_ChatLine]]:
    """Convert one AppSync event message into chat transcript lines."""

    should_stop, output_lines = _render_event_lines(message)
    return (
        should_stop,
        [
            _chat_line_from_payload(
                line,
                direction = "status" if "Received EXIT." in line else "inbound",
                current_time = current_time,
            )
            for line in output_lines
        ],
    )


def _build_chat_header_panel(
    notifier_domain: str,
    wallet_id: str
) -> Panel:
    """Build the top banner panel for the interactive chat app."""

    title = Text()
    title.append("pw chat", style = "bold #d7875f")
    title.append(" live", style = "#a9a9b3")
    body = Text(
        (
            f"Notifier: {normalize_domain_name(notifier_domain)}\n"
            f"Channel: {build_wallet_channel(wallet_id)}\n"
            "Enter sends a message. Type /quit to leave."
        ),
        style = "#a9a9b3",
    )
    return Panel(
        body,
        title = title,
        title_align = "left",
        border_style = "bold #d7875f",
        box = ROUNDED,
        expand = True,
        padding = (0, 1),
    )


def _should_use_textual_chat_view() -> bool:
    """Return whether `pw chat` should open the interactive terminal UI."""

    return (
        TEXTUAL_AVAILABLE
        and sys.stdin.isatty()
        and sys.stdout.isatty()
    )


@dataclass(frozen = True)
class _ChatSessionConfig:
    """Resolved connection settings for one chat session."""

    notifier_domain: str
    wallet_id: str
    auth_token: str
    test_publish: bool
    debug_payload: dict[str, object] | None


class _ChatTextualApp(App[None] if TEXTUAL_AVAILABLE else object):
    """TTY-only Textual chat app for `pw chat`."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #chat-header {
        margin: 0 0 1 0;
        height: auto;
    }

    #chat-log {
        height: 1fr;
        border: round #d7875f;
        padding: 0 1;
        background: #121416;
    }

    #chat-input {
        margin: 1 0 0 0;
    }
    """
    BINDINGS = [
        ("q", "request_quit", "Quit"),
        ("escape", "request_quit", "Quit"),
        ("ctrl+c", "request_quit", "Quit"),
        ("ctrl+w", "request_quit", "Quit"),
    ]

    def __init__(
        self,
        *,
        connection: AppSyncConnection,
        session: _ChatSessionConfig
    ) -> None:
        """Store the dependencies needed by the interactive chat app."""

        super().__init__()
        self._connection = connection
        self._session = session
        self._stop_event = threading.Event()
        self._outbound_queue: Queue[object] = Queue()
        self._worker_thread: threading.Thread | None = None
        self._exit_code = 0

    def compose(self) -> ComposeResult:
        """Compose the interactive chat layout."""

        yield Vertical(
            Static(
                _build_chat_header_panel(
                    self._session.notifier_domain,
                    self._session.wallet_id),
                id = "chat-header",
            ),
            RichLog(
                id = "chat-log",
                wrap = True,
                markup = True,
                highlight = False,
                auto_scroll = True,
            ),
            Input(
                placeholder = "Type a message and press Enter",
                id = "chat-input",
            ),
        )

    def on_mount(self, _event: events.Mount) -> None:
        """Start the background websocket worker after the UI mounts."""

        self._append_line(
            _chat_line_from_payload(
                "Connecting to notifier chat...",
                direction = "status",
            )
        )
        self._worker_thread = threading.Thread(
            target = self._run_worker,
            name = "pw-chat-worker",
            daemon = True,
        )
        self._worker_thread.start()

    def on_unmount(self, _event: events.Unmount) -> None:
        """Signal the worker thread to stop when the app closes."""

        self._stop_event.set()

    def _worker_enqueue(
        self,
        chat_line: _ChatLine
    ) -> None:
        """Forward one transcript line back to the UI thread."""

        self.call_from_thread(
            self._append_line,
            chat_line,
        )

    def _append_line(
        self,
        chat_line: _ChatLine
    ) -> None:
        """Append one styled line to the transcript view."""

        log = self.query_one("#chat-log", RichLog)
        log.write(Text.from_markup(chat_line.text, style = chat_line.style))

    def _run_worker(self) -> None:
        """Own the websocket lifecycle and relay transcript updates to the UI."""

        try:
            self._connection.connect()
            if self._session.test_publish:
                self._connection.publish("TEST")
                self._worker_enqueue(
                    _chat_line_from_payload(
                        "TEST",
                        direction = "outbound",
                    )
                )

            self._connection.subscribe()
            self._connection.set_timeout(CHAT_POLL_SECONDS)
            self._worker_enqueue(
                _chat_line_from_payload(
                    "Connected. Listening for events.",
                    direction = "status",
                )
            )

            if self._session.debug_payload is not None:
                self._worker_enqueue(
                    _chat_line_from_payload(
                        json.dumps(
                            self._session.debug_payload,
                            sort_keys = False,
                            ensure_ascii = False,
                            indent = 2,
                        ),
                        direction = "status",
                    )
                )

            while not self._stop_event.is_set():
                self._publish_pending_messages()
                message = self._connection.receive_event()
                if message is None:
                    continue

                should_stop, chat_lines = _chat_lines_from_event(message)
                for chat_line in chat_lines:
                    self._worker_enqueue(chat_line)

                if should_stop:
                    self._stop_event.set()
                    self.call_from_thread(self.exit)
                    return
        except KeyboardInterrupt:
            self._stop_event.set()
        except Exception as exc:
            self._exit_code = 1
            self._worker_enqueue(
                _chat_line_from_payload(
                    f"Error: {exc}",
                    direction = "status",
                )
            )
            self.call_from_thread(self.exit)
        finally:
            self._connection.close()

    def _publish_pending_messages(self) -> None:
        """Publish all queued outbound messages before polling for replies."""

        while not self._stop_event.is_set():
            try:
                payload = self._outbound_queue.get_nowait()
            except Empty:
                return

            self._connection.publish(payload)
            self._worker_enqueue(
                _chat_line_from_payload(
                    payload,
                    direction = "outbound",
                )
            )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Queue an outbound chat message when the user presses Enter."""

        submitted = event.value.strip()
        if not submitted:
            event.input.value = ""
            return

        if submitted.lower() in {"/quit", "/exit"}:
            event.input.value = ""
            self.action_request_quit()
            return

        self._outbound_queue.put(submitted)
        event.input.value = ""

    def action_request_quit(self) -> None:
        """Stop the background worker and close the chat app."""

        self._stop_event.set()
        self.exit()


def _run_plain_chat(
    connection: AppSyncConnection,
    *,
    notifier_domain: str,
    wallet_id: str,
    test: bool
) -> int:
    """Run the original print-based chat listener for non-interactive sessions."""

    try:
        print(
            f"Connecting to {build_websocket_url(notifier_domain)} on {build_wallet_channel(wallet_id)}..."
        )
        connection.connect()
        if test:
            connection.publish("TEST")
        connection.subscribe()
        print("Connected. Press Ctrl+C to stop listening.")
        connection.listen_forever()
    except KeyboardInterrupt:
        print("Stopping chat listener.")
    finally:
        connection.close()

    return 0


def cmd_chat(
    *,
    domain: str | None = None,
    debug: bool = False,
    test: bool = False,
    unsigned: bool = False,
    anonymous: bool = False,
    config_path: Path,
    require_configured_keys: Callable[[], None],
    load_signing_key_pair: Callable[[], KeyPair]
) -> int:
    """Connect to the configured notifier chat channel and stream events."""

    # Reuse the existing CLI validation so chat only runs after wallet setup.
    require_configured_keys()
    notifier_domain = domain or load_notifier_domain(config_path)
    wallet_id = "Anonymous" if anonymous else load_wallet_id(config_path)
    key_pair = load_signing_key_pair()
    auth_token = build_auth_token(
        key_pair,
        notifier_domain,
        wallet_id,
        unsigned = unsigned)

    debug_payload = {
        "WebSocketUrl": build_websocket_url(notifier_domain),
        "Channel": build_wallet_channel(wallet_id),
        "ConnectHeaders": build_websocket_headers(
            notifier_domain,
            auth_token),
        "SubscribeHeaders": build_subscribe_headers(
            notifier_domain,
            auth_token),
    }

    if debug and not _should_use_textual_chat_view():
        print_debug_payload(
            "Chat connection details",
            debug_payload,
        )

    connection = AppSyncConnection(
        notifier_domain,
        wallet_id,
        auth_token)

    if _should_use_textual_chat_view():
        app = _ChatTextualApp(
            connection = connection,
            session = _ChatSessionConfig(
                notifier_domain = notifier_domain,
                wallet_id = wallet_id,
                auth_token = auth_token,
                test_publish = test,
                debug_payload = debug_payload if debug else None,
            ),
        )
        app.run()
        return app._exit_code

    return _run_plain_chat(
        connection,
        notifier_domain = notifier_domain,
        wallet_id = wallet_id,
        test = test,
    )
