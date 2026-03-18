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

def test_send_onboard_message_posts_to_notifier_inbox(monkeypatch):
    """send_onboard_message sends a POST to the notifier inbox with the public key."""
    # Capture the outbound request for inspection
    captured_requests = []
    key_pair = cli.KeyPair()

    def fake_urlopen(request):
        captured_requests.append(request)
        return DummyResponse(
            cli.json.dumps({"Wallet": "wallet-abc-123"}).encode("utf-8")
        )

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    # Call with a fake PEM-encoded public key
    public_key_pem = b"-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEAtest==\n-----END PUBLIC KEY-----\n"

    result = cli.send_onboard_message(
        key_pair,
        public_key_pem,
        "any-notifier.pollyweb.org",
    )

    # Verify the request was sent to the correct URL
    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.full_url == f"https://pw.{cli.NOTIFIER_DOMAIN}/inbox"
    assert request.get_method() == "POST"
    assert request.headers["Content-type"] == "application/json"

    # Verify the request body contains the expected fields
    body = cli.json.loads(request.data.decode("utf-8"))
    assert body["Header"]["To"] == cli.NOTIFIER_DOMAIN
    assert body["Header"]["Subject"] == cli.NOTIFIER_SUBJECT
    assert body["Header"]["From"] == "Anonymous"
    assert body["Body"]["Language"] == cli.NOTIFIER_LANGUAGE
    assert body["Body"]["PublicKey"] == "MCowBQYDK2VwAyEAtest=="
    assert "Hash" not in body
    assert "Signature" not in body

    # Verify the parsed response is returned
    assert result == {"Wallet": "wallet-abc-123"}

def test_send_onboard_message_debug_prints_payloads(monkeypatch, capsys):
    """send_onboard_message prints outbound and inbound payloads in debug mode."""
    key_pair = cli.KeyPair()

    def fake_urlopen(request):
        """Return a stable notifier payload for debug output verification."""

        return DummyResponse(
            cli.json.dumps({"Wallet": "wallet-abc-123"}).encode("utf-8")
        )

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    cli.send_onboard_message(
        key_pair,
        b"-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEAtest==\n-----END PUBLIC KEY-----\n",
        "any-notifier.pollyweb.org",
        debug=True,
    )

    captured = capsys.readouterr()
    assert "Outbound payload to https://pw.any-notifier.pollyweb.org/inbox:" in captured.out
    assert "Subject: Onboard@Notifier" in captured.out
    assert "-----BEGIN PUBLIC KEY-----" not in captured.out
    assert "-----END PUBLIC KEY-----" not in captured.out
    assert "PublicKey:" in captured.out
    assert "MCowBQYDK2VwAyEAtest==" in captured.out
    assert "Hash:" not in captured.out
    assert "Signature:" not in captured.out
    assert "Inbound payload:" in captured.out
    assert "Wallet: wallet-abc-123" in captured.out

def test_send_onboard_message_returns_empty_dict_for_empty_response(monkeypatch):
    """send_onboard_message returns an empty dict when the server returns no body."""
    key_pair = cli.KeyPair()
    monkeypatch.setattr(
        cli.urllib.request, "urlopen", lambda r: DummyResponse(b"")
    )

    result = cli.send_onboard_message(
        key_pair,
        b"-----BEGIN PUBLIC KEY-----\ntest==\n-----END PUBLIC KEY-----\n",
        "any-notifier.pollyweb.org",
    )

    assert result == {}

def test_send_onboard_message_raises_for_non_dict_json_response(monkeypatch):
    """send_onboard_message raises ValueError when the response is not a JSON object."""
    key_pair = cli.KeyPair()
    monkeypatch.setattr(
        cli.urllib.request, "urlopen", lambda r: DummyResponse(b'["not", "a", "dict"]')
    )

    with pytest.raises(ValueError, match="must be a JSON object"):
        cli.send_onboard_message(
            key_pair,
            b"-----BEGIN PUBLIC KEY-----\ntest==\n-----END PUBLIC KEY-----\n",
            "any-notifier.pollyweb.org",
        )
