"""Interactive AppSync Events chat helpers for the CLI."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import secrets

from pollyweb import KeyPair, Msg, Wallet, normalize_domain_name
import yaml
from websocket import WebSocket
from websocket import WebSocketConnectionClosedException
from websocket import create_connection

from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.features.config import load_notifier_domain
from pollyweb_cli.tools.debug import print_debug_payload

DEFAULT_CHANNEL_NAMESPACE = "default"
CONNECT_SUBJECT = "Connect@Notifier"


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

        # Wait for the explicit publish success frame before subscribing.
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
                if _print_event_payload(message):
                    return
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

    payload = json.dumps(headers, separators=(",", ":")).encode("utf-8")
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


def _print_event_payload(message: dict[str, object]) -> bool:
    """Render one incoming AppSync event payload and report whether to stop."""

    event_list = message.get("event")
    if isinstance(event_list, list):
        for event in event_list:
            if _is_exit_payload(event):
                print("Received EXIT. Stopping chat listener.")
                return True
            if isinstance(event, str):
                print(event)
            else:
                print(json.dumps(event, sort_keys = True))
        return False

    payload = message.get("payload")
    if payload is not None:
        if _is_exit_payload(payload):
            print("Received EXIT. Stopping chat listener.")
            return True
        if isinstance(payload, str):
            print(payload)
        else:
            print(json.dumps(payload, sort_keys = True))
        return False

    print(json.dumps(message, sort_keys = True))
    return False


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


def cmd_chat(
    *,
    domain: str | None = None,
    debug: bool = False,
    test: bool = False,
    unsigned: bool = False,
    anonymous: bool = False,
    config_path: Path,
    require_configured_keys,
    load_signing_key_pair
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

    if debug:
        print_debug_payload(
            "Chat connection details",
            {
                "WebSocketUrl": build_websocket_url(notifier_domain),
                "Channel": build_wallet_channel(wallet_id),
                "ConnectHeaders": build_websocket_headers(
                    notifier_domain,
                    auth_token),
                "SubscribeHeaders": build_subscribe_headers(
                    notifier_domain,
                    auth_token),
            },
        )

    connection = AppSyncConnection(
        notifier_domain,
        wallet_id,
        auth_token)
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
