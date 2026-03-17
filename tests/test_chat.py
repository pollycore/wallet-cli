from __future__ import annotations

import builtins
import json
import socket
import stat
import sys
import uuid
import urllib.error
from pathlib import Path

import pollyweb.msg as pollyweb_msg
import pytest

from pollyweb import Msg
from pollyweb_cli import cli
from pollyweb_cli.features import chat as chat_feature
from pollyweb_cli.features import test as test_feature
from pollyweb_cli.tools import transport as transport_tools

from tests.cli_test_helpers import (
    TEST_MSGS_DIR,
    VALID_BIND,
    VALID_WALLET_ID,
    DummyResponse,
    FakeChatConnection,
    FakeReadline,
    _setup_sync_env,
    make_echo_response_payload,
)

def test_chat_builds_expected_event_endpoints():
    assert chat_feature.build_events_domain("any-notifier.pollyweb.org") == (
        "events.any-notifier.pollyweb.org"
    )
    assert chat_feature.build_websocket_url("any-notifier.pollyweb.org") == (
        "wss://events.any-notifier.pollyweb.org/event/realtime"
    )
    assert chat_feature.build_wallet_channel("wallet-uuid") == "/default/wallet-uuid"

def test_chat_marks_first_connection(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        f"Helpers:\n  Notifier: any-notifier.pollyweb.org\nWallet: {VALID_WALLET_ID}\n",
        encoding = "utf-8")
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)
    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(
        cli,
        "load_signing_key_pair",
        lambda: cli.KeyPair())
    created_connections: list[FakeChatConnection] = []

    def fake_connection(notifier_domain: str, wallet_id: str, auth_token: str):
        connection = FakeChatConnection(notifier_domain, wallet_id, auth_token)
        created_connections.append(connection)
        return connection

    monkeypatch.setattr(chat_feature, "AppSyncConnection", fake_connection)

    exit_code = cli.main(["chat"])

    assert exit_code == 0
    assert created_connections[0].calls == [
        "connect",
        "subscribe",
        "listen",
        "close",
    ]
    assert created_connections[0].auth_token
    captured = capsys.readouterr()
    assert "Connected. Press Ctrl+C to stop listening." in captured.out

def test_chat_test_flag_publishes_test_message(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        f"Helpers:\n  Notifier: any-notifier.pollyweb.org\nWallet: {VALID_WALLET_ID}\n",
        encoding = "utf-8")
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)
    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(
        cli,
        "load_signing_key_pair",
        lambda: cli.KeyPair())
    created_connections: list[FakeChatConnection] = []

    def fake_connection(notifier_domain: str, wallet_id: str, auth_token: str):
        connection = FakeChatConnection(notifier_domain, wallet_id, auth_token)
        created_connections.append(connection)
        return connection

    monkeypatch.setattr(chat_feature, "AppSyncConnection", fake_connection)

    exit_code = cli.main(["chat", "--test"])

    assert exit_code == 0
    assert created_connections[0].calls == [
        "connect",
        "publish:TEST",
        "subscribe",
        "listen",
        "close",
    ]
    captured = capsys.readouterr()
    assert "Connected. Press Ctrl+C to stop listening." in captured.out

def test_chat_debug_prints_connection_details(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        f"Helpers:\n  Notifier: any-notifier.pollyweb.org\nWallet: {VALID_WALLET_ID}\n",
        encoding = "utf-8")
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)
    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(
        cli,
        "load_signing_key_pair",
        lambda: cli.KeyPair())
    monkeypatch.setattr(chat_feature, "AppSyncConnection", FakeChatConnection)

    exit_code = cli.main(["chat", "--debug"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "\nChat connection details:\n" in captured.out
    assert "WebSocketUrl: wss://events.any-notifier.pollyweb.org/event/realtime" in captured.out
    assert f"Channel: /default/{VALID_WALLET_ID}" in captured.out
    assert "ConnectHeaders:" in captured.out
    assert "SubscribeHeaders:" in captured.out

def test_chat_domain_argument_overrides_config_notifier(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        f"Helpers:\n  Notifier: any-notifier.pollyweb.org\nWallet: {VALID_WALLET_ID}\n",
        encoding = "utf-8")
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)
    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(
        cli,
        "load_signing_key_pair",
        lambda: cli.KeyPair())
    created_connections: list[FakeChatConnection] = []

    def fake_connection(notifier_domain: str, wallet_id: str, auth_token: str):
        connection = FakeChatConnection(notifier_domain, wallet_id, auth_token)
        created_connections.append(connection)
        return connection

    monkeypatch.setattr(chat_feature, "AppSyncConnection", fake_connection)

    exit_code = cli.main(["chat", "override.example.com", "--debug", "--test"])

    assert exit_code == 0
    assert created_connections[0].notifier_domain == "override.example.com"
    assert created_connections[0].calls == [
        "connect",
        "publish:TEST",
        "subscribe",
        "listen",
        "close",
    ]
    captured = capsys.readouterr()
    assert "wss://events.override.example.com/event/realtime" in captured.out

def test_chat_builds_signed_auth_token():
    key_pair = cli.KeyPair()

    token = chat_feature.build_auth_token(
        key_pair,
        "any-notifier.pollyweb.org",
        VALID_WALLET_ID)

    padded = token + "=" * (-len(token) % 4)
    payload = json.loads(
        __import__("base64").urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    message = Msg.load(payload)

    assert message.Subject == "Connect@Notifier"
    assert message.To == "any-notifier.pollyweb.org"
    assert message.to_dict()["Body"]["Wallet"] == VALID_WALLET_ID
    assert message.verify(key_pair.PublicKey) is True

def test_chat_builds_unsigned_auth_token():
    key_pair = cli.KeyPair()

    token = chat_feature.build_auth_token(
        key_pair,
        "any-notifier.pollyweb.org",
        VALID_WALLET_ID,
        unsigned = True)

    padded = token + "=" * (-len(token) % 4)
    payload = json.loads(
        __import__("base64").urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))

    assert payload["Header"]["Subject"] == "Connect@Notifier"
    assert payload["Header"]["To"] == "any-notifier.pollyweb.org"
    assert payload["Header"]["From"] == "Anonymous"
    assert payload["Body"]["Wallet"] == VALID_WALLET_ID
    assert "Hash" not in payload
    assert "Signature" not in payload

def test_chat_anonymous_flag_uses_anonymous_wallet_channel(
    monkeypatch, tmp_path, capsys
):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"Helpers:\n  Notifier: any-notifier.pollyweb.org\nWallet: {VALID_WALLET_ID}\n",
        encoding = "utf-8")

    seen = {}

    def fake_connection(notifier_domain: str, wallet_id: str, auth_token: str):
        seen["notifier_domain"] = notifier_domain
        seen["wallet_id"] = wallet_id
        seen["auth_token"] = auth_token
        return FakeChatConnection(notifier_domain, wallet_id, auth_token)

    monkeypatch.setattr(chat_feature, "AppSyncConnection", fake_connection)

    exit_code = chat_feature.cmd_chat(
        domain = None,
        debug = False,
        test = False,
        unsigned = False,
        anonymous = True,
        config_path = config_path,
        require_configured_keys = lambda: None,
        load_signing_key_pair = cli.KeyPair,
    )

    assert exit_code == 0
    assert seen["notifier_domain"] == "any-notifier.pollyweb.org"
    assert seen["wallet_id"] == "Anonymous"
    captured = capsys.readouterr()
    assert "/default/Anonymous" in captured.out

def test_chat_exit_payload_stops_listener(capsys):
    should_stop = chat_feature._print_event_payload(
        {"event": ["EXIT"]})

    assert should_stop is True
    captured = capsys.readouterr()
    assert "Received EXIT. Stopping chat listener." in captured.out

def test_chat_exit_message_payload_stops_listener(capsys):
    should_stop = chat_feature._print_event_payload(
        {"payload": {"message": "EXIT"}})

    assert should_stop is True
    captured = capsys.readouterr()
    assert "Received EXIT. Stopping chat listener." in captured.out

def test_chat_listener_exits_when_event_requests_exit(capsys):
    connection = chat_feature.AppSyncConnection(
        "any-notifier.pollyweb.org",
        VALID_WALLET_ID,
        "signed-token")
    messages = iter(
        [
            {"type": "keepalive"},
            {"type": "data", "payload": {"message": "EXIT"}},
        ]
    )

    connection._recv_json = lambda: next(messages)

    connection.listen_forever()

    captured = capsys.readouterr()
    assert "Received EXIT. Stopping chat listener." in captured.out

def test_chat_publish_sends_test_event_and_waits_for_publish_success():
    class FakeWebSocket:
        def __init__(self):
            self.sent_payloads: list[str] = []

        def send(self, payload: str) -> None:
            self.sent_payloads.append(payload)

    connection = chat_feature.AppSyncConnection(
        "any-notifier.pollyweb.org",
        VALID_WALLET_ID,
        "signed-token")
    connection.websocket = FakeWebSocket()
    messages = iter(
        [
            {"type": "keepalive"},
            {"type": "publish_success"},
        ]
    )

    connection._recv_json = lambda: next(messages)

    connection.publish("TEST")

    assert len(connection.websocket.sent_payloads) == 1
    payload = json.loads(connection.websocket.sent_payloads[0])
    assert payload["type"] == "publish"
    assert payload["channel"] == f"/default/{VALID_WALLET_ID}"
    assert payload["events"] == ['"TEST"']
    assert payload["authorization"]["Authorization"] == "signed-token"

def test_chat_requires_wallet_in_config(tmp_path):
    config_dir = tmp_path / ".pollyweb"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text("Helpers:\n  Notifier: any-notifier.pollyweb.org\n", encoding = "utf-8")

    with pytest.raises(cli.UserFacingError):
        chat_feature.load_wallet_id(config_path)

