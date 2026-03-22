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

def test_config_creates_keypair_files(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)
    monkeypatch.setattr(
        cli,
        "send_onboard_message",
        lambda key_pair, public_key, notifier_domain, debug=False: {},
    )

    exit_code = cli.main(["config"])

    assert exit_code == 0
    assert private_key_path.exists()
    assert public_key_path.exists()
    assert config_path.exists()
    assert private_key_path.read_text().startswith("-----BEGIN PRIVATE KEY-----")
    assert public_key_path.read_text().startswith("-----BEGIN PUBLIC KEY-----")
    assert cli.yaml.safe_load(config_path.read_text()) == {
        "Helpers": {"Buffer": "any-notifier.pollyweb.org"}
    }

    captured = capsys.readouterr()
    assert str(private_key_path) in captured.out
    assert str(public_key_path) in captured.out
    assert str(config_path) in captured.out

def test_config_is_idempotent_when_keys_already_exist(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    config_dir.mkdir()
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"
    private_key_path.write_text("existing-private")
    public_key_path.write_text("existing-public")
    config_path.write_text("Helpers:\n  Buffer: any-notifier.pollyweb.org\n")
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)

    exit_code = cli.main(["config"])

    assert exit_code == 0
    assert private_key_path.read_text() == "existing-private"
    assert public_key_path.read_text() == "existing-public"
    assert config_path.read_text() == "Helpers:\n  Buffer: any-notifier.pollyweb.org\n"

    captured = capsys.readouterr()
    assert str(private_key_path) in captured.out
    assert str(public_key_path) in captured.out
    assert str(config_path) in captured.out
    assert captured.err == ""

def test_config_refuses_partial_configuration_without_force(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    config_dir.mkdir()
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"
    private_key_path.write_text("existing-private")

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)

    exit_code = cli.main(["config"])

    assert exit_code == 1
    assert private_key_path.read_text() == "existing-private"
    assert not public_key_path.exists()

    captured = capsys.readouterr()
    assert "partially configured" in captured.err

def test_config_force_overwrites_existing_keys(monkeypatch, tmp_path):
    """config --force replaces keys and rewrites the default config file."""

    config_dir = tmp_path / ".pollyweb"
    config_dir.mkdir()
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"
    private_key_path.write_text("existing-private")
    public_key_path.write_text("existing-public")
    config_path.write_text("Helpers:\n  Notifier: old.example.com\n")
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)
    monkeypatch.setattr(
        cli,
        "send_onboard_message",
        lambda key_pair, public_key, notifier_domain, debug=False: {},
    )

    exit_code = cli.main(["config", "--force"])

    assert exit_code == 0
    assert private_key_path.read_text() != "existing-private"
    assert public_key_path.read_text() != "existing-public"
    assert cli.yaml.safe_load(config_path.read_text()) == {
        "Helpers": {"Buffer": "any-notifier.pollyweb.org"}
    }

def test_config_sets_expected_permissions(monkeypatch, tmp_path):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)

    exit_code = cli.main(["config"])

    assert exit_code == 0
    assert stat.S_IMODE(private_key_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(public_key_path.stat().st_mode) == 0o644
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600

def test_config_onboards_with_configured_notifier(monkeypatch, tmp_path):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"
    send_calls: list[tuple[bytes, bytes, str]] = []

    def fake_send_onboard_message(
        key_pair,
        public_key: bytes,
        notifier_domain: str,
        debug: bool = False
    ) -> dict[str, object]:
        """Capture notifier onboarding requests without performing I/O."""

        send_calls.append(
            (
                key_pair.public_pem_bytes(),
                public_key,
                notifier_domain,
            )
        )
        return {}

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)
    monkeypatch.setattr(cli, "send_onboard_message", fake_send_onboard_message)

    exit_code = cli.main(["config"])

    assert exit_code == 0
    assert len(send_calls) == 1
    assert send_calls[0][2] == "any-notifier.pollyweb.org"
    assert send_calls[0][0] == public_key_path.read_bytes()
    assert send_calls[0][1] == public_key_path.read_bytes()

def test_cmd_config_prints_wallet_from_onboard_response(monkeypatch, tmp_path, capsys):
    """cmd_config prints the Wallet value returned by the notifier after key creation."""
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)

    # Simulate the notifier returning a wallet address
    monkeypatch.setattr(
        cli,
        "send_onboard_message",
        lambda key_pair, public_key, notifier_domain, debug=False: {"Wallet": "wallet-xyz-999"},
    )

    exit_code = cli.main(["config"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Wallet: wallet-xyz-999" in captured.out

def test_cmd_config_persists_onboard_response_in_config(monkeypatch, tmp_path):
    """cmd_config stores broker and wallet values returned by onboarding."""

    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)
    monkeypatch.setattr(
        cli,
        "send_onboard_message",
        lambda key_pair, public_key, notifier_domain, debug=False: {
            "Broker": "any-broker.pollyweb.org",
            "Wallet": "wallet-xyz-999",
        },
    )

    exit_code = cli.main(["config"])

    assert exit_code == 0
    assert cli.yaml.safe_load(config_path.read_text()) == {
        "Helpers": {
            "Buffer": "any-notifier.pollyweb.org",
            "Broker": "any-broker.pollyweb.org",
        },
        "Wallet": "wallet-xyz-999",
    }

def test_cmd_config_silently_ignores_onboard_network_error(monkeypatch, tmp_path, capsys):
    """cmd_config succeeds even when the notifier is unreachable."""
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)

    def failing_onboard(_key_pair, _public_key, _notifier_domain, debug=False):
        raise cli.urllib.error.URLError("connection refused")

    monkeypatch.setattr(cli, "send_onboard_message", failing_onboard)

    exit_code = cli.main(["config"])

    # Key creation should still succeed despite the notifier being down
    assert exit_code == 0
    assert private_key_path.exists()
    assert public_key_path.exists()
    captured = capsys.readouterr()
    assert "Wallet" not in captured.out
    assert captured.err == ""
    assert cli.yaml.safe_load(config_path.read_text()) == {
        "Helpers": {"Buffer": "any-notifier.pollyweb.org"}
    }

def test_cmd_config_silently_ignores_onboard_value_error(monkeypatch, tmp_path, capsys):
    """cmd_config succeeds even when the notifier returns an unexpected response."""
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)

    def bad_onboard(_key_pair, _public_key, _notifier_domain, debug=False):
        raise ValueError("Notifier onboard response must be a JSON object.")

    monkeypatch.setattr(cli, "send_onboard_message", bad_onboard)

    exit_code = cli.main(["config"])

    assert exit_code == 0
    assert private_key_path.exists()
    captured = capsys.readouterr()
    assert "Wallet" not in captured.out
    assert captured.err == ""

def test_cmd_config_does_not_print_wallet_when_absent_from_response(monkeypatch, tmp_path, capsys):
    """cmd_config does not print a Wallet line when the notifier omits it."""
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)

    # Notifier responds but without a Wallet field
    monkeypatch.setattr(
        cli,
        "send_onboard_message",
        lambda key_pair, public_key, notifier_domain, debug=False: {"Status": "ok"},
    )

    exit_code = cli.main(["config"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Wallet" not in captured.out

def test_cmd_config_debug_prints_notifier_payloads(monkeypatch, tmp_path, capsys):
    """cmd_config --debug prints the notifier request and response payloads."""

    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)
    monkeypatch.setattr(
        cli.urllib.request,
        "urlopen",
        lambda request: DummyResponse(
            cli.json.dumps({"Wallet": "wallet-debug-123"}).encode("utf-8")
        ),
    )

    exit_code = cli.main(["config", "--debug"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Outbound payload to https://pw.any-notifier.pollyweb.org/inbox:" in captured.out
    assert "Subject: Onboard@Notifier" in captured.out
    assert "-----BEGIN PUBLIC KEY-----" not in captured.out
    assert "-----END PUBLIC KEY-----" not in captured.out
    assert "Inbound payload:" in captured.out
    assert "Wallet: wallet-debug-123" in captured.out

