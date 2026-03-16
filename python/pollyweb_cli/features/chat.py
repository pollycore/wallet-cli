"""Interactive AppSync Events chat helpers for the CLI."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import secrets

import yaml
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import Session
from websocket import WebSocket
from websocket import WebSocketConnectionClosedException
from websocket import create_connection

from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.features.config import load_notifier_domain


CHAT_STATE_FILE_NAME = "chat.yaml"
DEFAULT_CHANNEL_NAMESPACE = "default"
APP_SYNC_SERVICE = "appsync"
APP_SYNC_REGION = "us-east-1"


@dataclass
class SignedHeaders:
    """Store the IAM authorization headers used by AppSync Events."""

    host: str
    headers: dict[str, str]


class AppSyncConnection:
    """Wrap a websocket connection to the notifier AppSync Events API."""

    def __init__(
        self,
        notifier_domain: str,
        wallet_id: str,
        websocket_factory = create_connection,
        aws_session_factory = Session
    ) -> None:
        """Initialize the connection dependencies for a notifier chat session."""

        # Keep the raw notifier domain so the CLI can print it in status messages.
        self.notifier_domain = notifier_domain

        # Reuse the wallet identifier as the subscription channel suffix.
        self.wallet_id = wallet_id

        # Allow tests to replace the websocket creation logic with a stub.
        self.websocket_factory = websocket_factory

        # Allow tests to inject credentials without touching real AWS config.
        self.aws_session_factory = aws_session_factory

        # Track the underlying websocket so shutdown can unsubscribe cleanly.
        self.websocket: WebSocket | None = None

        # Reuse the generated subscribe ID during unsubscribe.
        self.subscription_id = secrets.token_hex(8)

        # Cache the current subscription channel string.
        self.channel = build_wallet_channel(wallet_id)

    def connect(self) -> None:
        """Open the websocket, then finish the AppSync Events handshake."""

        signed_headers = build_websocket_authorization(
            self.notifier_domain,
            aws_session_factory = self.aws_session_factory)
        protocol_headers = [
            "aws-appsync-event-ws",
            f"header-{_encode_header_payload(signed_headers.headers)}",
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

        authorization = build_message_authorization(
            self.notifier_domain,
            aws_session_factory = self.aws_session_factory)
        self._send_json(
            {
                "id": self.subscription_id,
                "type": "subscribe",
                "channel": self.channel,
                "authorization": authorization,
            }
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

    def publish_test_message(self) -> None:
        """Publish a one-time test event into the wallet channel."""

        authorization = build_message_authorization(
            self.notifier_domain,
            aws_session_factory = self.aws_session_factory)
        payload = {
            "message": "Notifier chat connection established.",
            "source": self.notifier_domain,
            "metadata": {
                "kind": "test",
                "wallet": self.wallet_id,
            },
        }
        self._send_json(
            {
                "id": secrets.token_hex(8),
                "type": "publish",
                "channel": self.channel,
                "events": [json.dumps(payload, separators=(",", ":"))],
                "authorization": authorization,
            }
        )

        # Confirm the publish before declaring the first-time setup complete.
        while True:
            response = self._recv_json()
            response_type = response.get("type")
            if response_type == "publish_success":
                return
            if response_type in {"ka", "keepalive"}:
                continue
            if response_type == "data":
                _print_event_payload(response)
                continue
            raise UserFacingError(
                f"Chat publish failed: expected publish_success, received {response}."
            )

    def listen_forever(self) -> None:
        """Print chat events until the user interrupts the process."""

        while True:
            try:
                message = self._recv_json()
            except KeyboardInterrupt:
                raise
            except WebSocketConnectionClosedException as exc:
                raise UserFacingError("Chat connection closed unexpectedly.") from exc

            message_type = message.get("type")
            if message_type in {"ka", "keepalive"}:
                continue
            if message_type == "data":
                _print_event_payload(message)
                continue
            if message_type == "error":
                raise UserFacingError(f"Chat stream returned an error: {message}")

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
        self.websocket.send(json.dumps(payload, separators=(",", ":")))

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

    return f"events.{notifier_domain}"


def build_websocket_url(notifier_domain: str) -> str:
    """Build the websocket endpoint URL for a notifier."""

    return f"wss://{build_events_domain(notifier_domain)}/event/realtime"


def build_wallet_channel(wallet_id: str) -> str:
    """Build the AppSync Events channel used for one wallet."""

    return f"/{DEFAULT_CHANNEL_NAMESPACE}/{wallet_id}"


def build_websocket_authorization(
    notifier_domain: str,
    aws_session_factory = Session
) -> SignedHeaders:
    """Build SigV4 headers for the websocket connect request."""

    events_domain = build_events_domain(notifier_domain)
    request = AWSRequest(
        method = "POST",
        url = f"https://{events_domain}/event",
        data = "{}")
    headers = _sign_request(
        request,
        aws_session_factory = aws_session_factory)
    return SignedHeaders(
        host = events_domain,
        headers = headers)


def build_message_authorization(
    notifier_domain: str,
    aws_session_factory = Session
) -> dict[str, str]:
    """Build SigV4 headers for subscribe and publish websocket messages."""

    events_domain = build_events_domain(notifier_domain)
    request = AWSRequest(
        method = "POST",
        url = f"https://{events_domain}/event",
        data = "{}")
    headers = _sign_request(
        request,
        aws_session_factory = aws_session_factory)
    return headers


def _sign_request(
    request: AWSRequest,
    aws_session_factory = Session
) -> dict[str, str]:
    """Resolve AWS credentials and sign the request headers with SigV4."""

    profile_name = os.environ.get("AWS_PROFILE")
    session = aws_session_factory(profile = profile_name) if profile_name else aws_session_factory()
    credentials = session.get_credentials()
    if credentials is None:
        raise UserFacingError(
            "Missing AWS credentials for AppSync chat. Configure AWS_IAM credentials first."
        )

    frozen_credentials = credentials.get_frozen_credentials()
    normalized_headers = {
        str(header_name).lower(): str(header_value)
        for header_name, header_value in request.headers.items()
    }
    normalized_headers.setdefault("accept", "application/json, text/javascript")
    normalized_headers.setdefault("content-encoding", "amz-1.0")
    normalized_headers.setdefault("content-type", "application/json; charset=UTF-8")
    normalized_headers["host"] = request.url.split("/")[2]

    for header_name, header_value in normalized_headers.items():
        request.headers[header_name] = header_value

    SigV4Auth(
        frozen_credentials,
        APP_SYNC_SERVICE,
        APP_SYNC_REGION).add_auth(request)

    # Preserve only the headers AppSync requires for IAM websocket operations.
    signed_headers = {
        "accept": "application/json, text/javascript",
        "content-encoding": "amz-1.0",
        "content-type": "application/json; charset=UTF-8",
        "host": request.url.split("/")[2],
    }

    normalized_signed_headers = {
        str(header_name).lower(): str(header_value)
        for header_name, header_value in request.headers.items()
    }

    for header_name in [
        "x-amz-date",
        "x-amz-security-token",
        "authorization",
    ]:
        value = normalized_signed_headers.get(header_name)
        if value:
            signed_headers[header_name] = value

    return signed_headers


def _encode_header_payload(headers: dict[str, str]) -> str:
    """Encode the auth headers using URL-safe base64 without padding."""

    payload = json.dumps(headers, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _print_event_payload(message: dict[str, object]) -> None:
    """Render one incoming AppSync event payload to stdout."""

    event_list = message.get("event")
    if isinstance(event_list, list):
        for event in event_list:
            if isinstance(event, str):
                print(event)
            else:
                print(json.dumps(event, sort_keys = True))
        return

    payload = message.get("payload")
    if payload is not None:
        if isinstance(payload, str):
            print(payload)
        else:
            print(json.dumps(payload, sort_keys = True))
        return

    print(json.dumps(message, sort_keys = True))


def load_wallet_id(
    config_path: Path
) -> str:
    """Read the configured wallet identifier from the wallet config."""

    if not config_path.exists():
        raise UserFacingError("Missing wallet configuration. Run `pw config` first.")

    config_payload = yaml.safe_load(config_path.read_text(encoding = "utf-8")) or {}
    if not isinstance(config_payload, dict):
        raise UserFacingError("Wallet configuration is invalid.")

    wallet_id = config_payload.get("Wallet")
    if not isinstance(wallet_id, str) or not wallet_id.strip():
        raise UserFacingError(
            "Missing Wallet in ~/.pollyweb/config.yaml. Run `pw config` again first."
        )

    return wallet_id.strip()


def load_chat_state(
    chat_state_path: Path
) -> dict[str, object]:
    """Load the persisted chat state, falling back to an empty dictionary."""

    if not chat_state_path.exists():
        return {}

    payload = yaml.safe_load(chat_state_path.read_text(encoding = "utf-8")) or {}
    if isinstance(payload, dict):
        return payload
    return {}


def has_connected_before(
    notifier_domain: str,
    chat_state_path: Path
) -> bool:
    """Return whether a notifier already received its one-time test message."""

    payload = load_chat_state(chat_state_path)
    connected = payload.get("ConnectedNotifiers")
    if not isinstance(connected, list):
        return False
    return notifier_domain in connected


def mark_connected(
    notifier_domain: str,
    chat_state_path: Path
) -> None:
    """Persist that the notifier already received its test message."""

    payload = load_chat_state(chat_state_path)
    connected = payload.get("ConnectedNotifiers")
    if not isinstance(connected, list):
        connected = []

    if notifier_domain not in connected:
        connected.append(notifier_domain)
    payload["ConnectedNotifiers"] = connected

    chat_state_path.parent.mkdir(mode = 0o700, parents = True, exist_ok = True)
    chat_state_path.write_text(
        yaml.safe_dump(
            payload,
            sort_keys = False),
        encoding = "utf-8")
    chat_state_path.chmod(0o600)


def cmd_chat(
    *,
    config_dir: Path,
    config_path: Path,
    require_configured_keys
) -> int:
    """Connect to the configured notifier chat channel and stream events."""

    # Reuse the existing CLI validation so chat only runs after wallet setup.
    require_configured_keys()
    notifier_domain = load_notifier_domain(config_path)
    wallet_id = load_wallet_id(config_path)
    chat_state_path = config_dir / CHAT_STATE_FILE_NAME
    is_first_connection = not has_connected_before(notifier_domain, chat_state_path)

    connection = AppSyncConnection(
        notifier_domain,
        wallet_id)
    try:
        print(
            f"Connecting to {build_websocket_url(notifier_domain)} on {build_wallet_channel(wallet_id)}..."
        )
        connection.connect()
        connection.subscribe()
        print("Connected. Press Ctrl+C to stop listening.")

        if is_first_connection:
            connection.publish_test_message()
            mark_connected(notifier_domain, chat_state_path)

        connection.listen_forever()
    except KeyboardInterrupt:
        print("Stopping chat listener.")
    finally:
        connection.close()

    return 0
