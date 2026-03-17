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

def test_echo_sends_signed_message_and_verifies_response(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    remote_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        assert payload["Header"]["To"] == "vault.example.com"
        assert payload["Header"]["Subject"] == "Echo@Domain"
        assert payload["Header"]["From"] == "Anonymous"

        # Reply From: vault.example.com To: vault.example.com
        return DummyResponse(
            make_echo_response_payload(
                from_value="vault.example.com",
                correlation=payload["Header"]["Correlation"],
                private_key=remote_key_pair.PrivateKey,
            )
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        pollyweb_msg,
        "_resolve_dkim_public_key",
        lambda domain, selector: (remote_key_pair.PublicKey, "ed25519"),
    )

    exit_code = cli.main(["echo", "vault.example.com"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "\nEcho response:\n" in captured.out
    assert "Subject: Echo@Domain" in captured.out
    assert "Echo: ok" in captured.out
    assert "Verified echo response: ✅" in captured.out
    assert captured.err == ""

def test_echo_fails_when_signature_does_not_verify(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    remote_key_pair = cli.KeyPair()
    wrong_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        return DummyResponse(
            make_echo_response_payload(
                from_value="vault.example.com",
                correlation=payload["Header"]["Correlation"],
                private_key=remote_key_pair.PrivateKey,
            )
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        pollyweb_msg,
        "_resolve_dkim_public_key",
        lambda domain, selector: (wrong_key_pair.PublicKey, "ed25519"),
    )

    exit_code = cli.main(["echo", "vault.example.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "did not verify" in captured.err
    assert "Invalid signature" in captured.err

def test_echo_fails_when_response_headers_do_not_make_sense(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    remote_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        return DummyResponse(
            make_echo_response_payload(
                from_value="other.example.com",
                correlation=payload["Header"]["Correlation"],
                private_key=remote_key_pair.PrivateKey,
            )
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        pollyweb_msg,
        "_resolve_dkim_public_key",
        lambda domain, selector: (remote_key_pair.PublicKey, "ed25519"),
    )

    exit_code = cli.main(["echo", "vault.example.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "unexpected From value: other.example.com" in captured.err

def test_echo_debug_prints_outbound_and_inbound_payloads(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    remote_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        return DummyResponse(
            make_echo_response_payload(
                from_value="vault.example.com",
                correlation=payload["Header"]["Correlation"],
                private_key=remote_key_pair.PrivateKey,
            )
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        pollyweb_msg,
        "_resolve_dkim_public_key",
        lambda domain, selector: (remote_key_pair.PublicKey, "ed25519"),
    )

    exit_code = cli.main(["echo", "--debug", "vault.example.com"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "\nOutbound payload to https://pw.vault.example.com/inbox:\n" in captured.out
    assert "Subject: Echo@Domain" in captured.out
    assert "To: vault.example.com" in captured.out
    assert "From: Anonymous" in captured.out.split("\n\nInbound payload:\n", 1)[0]
    assert "\n\nInbound payload:\n" in captured.out
    assert "From: vault.example.com" in captured.out
    assert "Echo: ok" in captured.out
    assert "Verified echo response from vault.example.com:" in captured.out
    assert " - Schema validated: pollyweb.org/MSG:1.0" in captured.out
    assert " - Required signed headers were present" in captured.out
    assert " - Canonical payload hash matched the signed content" in captured.out
    assert " - Signature verified via DKIM lookup for selector default on vault.example.com" in captured.out
    assert " - From matched expected domain: vault.example.com" in captured.out
    assert " - To matched expected sender: vault.example.com" in captured.out
    assert " - Subject matched expected echo subject: Echo@Domain" in captured.out
    assert captured.err == ""

def test_echo_debug_prints_outbound_and_inbound_payloads_for_dom_alias(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    remote_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        assert request.full_url == "https://pw.any-domain.pollyweb.org/inbox"
        assert payload["Header"]["To"] == "any-domain.pollyweb.org"
        assert payload["Header"]["From"] == "Anonymous"
        assert "Hash" not in payload
        assert "Signature" not in payload
        return DummyResponse(
            make_echo_response_payload(
                from_value = "any-domain.pollyweb.org",
                correlation = payload["Header"]["Correlation"],
                private_key = remote_key_pair.PrivateKey,
            )
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        pollyweb_msg,
        "_resolve_dkim_public_key",
        lambda domain, selector: (remote_key_pair.PublicKey, "ed25519"),
    )

    exit_code = cli.main(["echo", "--debug", "any-domain.dom"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert (
        "\nOutbound payload to https://pw.any-domain.pollyweb.org/inbox:\n"
        in captured.out
    )
    assert "Subject: Echo@Domain" in captured.out
    assert "To: any-domain.pollyweb.org" in captured.out
    outbound = captured.out.split("\n\nInbound payload:\n", 1)[0]
    assert "From: Anonymous" in outbound
    assert "Hash:" not in outbound
    assert "Signature:" not in outbound
    assert "\n\nInbound payload:\n" in captured.out
    assert "From: any-domain.pollyweb.org" in captured.out
    assert "Echo: ok" in captured.out
    assert "Verified echo response from any-domain.dom:" in captured.out
    assert (
        " - Signature verified via DKIM lookup for selector default "
        "on any-domain.pollyweb.org" in captured.out
    )
    assert " - From matched expected domain: any-domain.pollyweb.org" in captured.out
    assert " - To matched expected sender: any-domain.pollyweb.org" in captured.out
    assert captured.err == ""


def test_echo_accepts_response_to_stored_bind(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    remote_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump(
            [
                {
                    "Bind": VALID_WALLET_ID,
                    "Domain": "any-hoster.pollyweb.org",
                }
            ]
        ),
        encoding = "utf-8",
    )

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        return DummyResponse(
            make_echo_response_payload(
                from_value = "any-hoster.pollyweb.org",
                to_value = VALID_WALLET_ID,
                correlation = payload["Header"]["Correlation"],
                private_key = remote_key_pair.PrivateKey,
            )
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        pollyweb_msg,
        "_resolve_dkim_public_key",
        lambda domain, selector: (remote_key_pair.PublicKey, "ed25519"),
    )

    exit_code = cli.main(["echo", "any-hoster.pollyweb.org"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Verified echo response: ✅" in captured.out
    assert captured.err == ""


def test_echo_rejects_unrelated_response_to_value(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    remote_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump(
            [
                {
                    "Bind": VALID_WALLET_ID,
                    "Domain": "vault.example.com",
                }
            ]
        ),
        encoding = "utf-8",
    )

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        return DummyResponse(
            make_echo_response_payload(
                from_value = "vault.example.com",
                to_value = "30ddc4c7-ba23-4bae-971c-2595143f69eb",
                correlation = payload["Header"]["Correlation"],
                private_key = remote_key_pair.PrivateKey,
            )
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        pollyweb_msg,
        "_resolve_dkim_public_key",
        lambda domain, selector: (remote_key_pair.PublicKey, "ed25519"),
    )

    exit_code = cli.main(["echo", "vault.example.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert (
        "unexpected To value: 30ddc4c7-ba23-4bae-971c-2595143f69eb"
        in captured.err
    )

def test_print_echo_response_formats_payload(capsys):
    cli.print_echo_response(
        '{"Header":{"Subject":"Echo@Domain"},"Body":{"Echo":"ok"}}'
    )

    captured = capsys.readouterr()
    assert "\nEcho response:\n" in captured.out
    assert "Subject: Echo@Domain" in captured.out
    assert "Echo: ok" in captured.out
