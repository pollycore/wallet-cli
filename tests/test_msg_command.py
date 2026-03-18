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

def test_msg_loads_top_level_message_file_and_prints_response(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    message_path = tmp_path / "message.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    message_path.write_text(
        "To: vault.example.com\nSubject: Echo@Domain\nBody:\n  Ping: pong\n",
        encoding = "utf-8")

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        assert request.full_url == "https://pw.vault.example.com/inbox"
        assert payload["Header"]["To"] == "vault.example.com"
        assert payload["Header"]["Subject"] == "Echo@Domain"
        assert payload["Body"] == {"Ping": "pong"}
        return DummyResponse(b'{"ok":true}')

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["msg", str(message_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "ok: true"

def test_msg_uses_stored_bind_as_wallet_sender_for_target_domain(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    message_path = tmp_path / "message.yaml"
    bind_value = "30ddc4c7-ba23-4bae-971c-2595143f69eb"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump(
            [
                {
                    "Bind": bind_value,
                    "Domain": "any-hoster.pollyweb.org",
                }
            ],
            sort_keys = False),
        encoding = "utf-8")
    message_path.write_text(
        "To: any-hoster.dom\nSubject: Echo@Domain\nBody:\n  Ping: pong\n",
        encoding = "utf-8")

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))

        # The wallet-backed send should reuse the stored bind for the
        # normalized recipient domain instead of signing as Anonymous.
        assert payload["Header"]["From"] == bind_value
        assert payload["Header"]["To"] == "any-hoster.pollyweb.org"
        return DummyResponse(b'{"ok":true}')

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(transport_tools, "DEFAULT_BINDS_PATH", binds_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["msg", str(message_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "ok: true"

def test_msg_uses_wallet_default_anonymous_sender_when_no_bind_exists(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    message_path = tmp_path / "message.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    message_path.write_text(
        "To: vault.example.com\nSubject: Echo@Domain\nBody:\n  Ping: pong\n",
        encoding = "utf-8")

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))

        # When no stored bind exists, the CLI should leave sender fallback to
        # the wallet library, which still signs as Anonymous by default.
        assert payload["Header"]["From"] == "Anonymous"
        assert payload["Header"]["To"] == "vault.example.com"
        return DummyResponse(b'{"ok":true}')

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(transport_tools, "DEFAULT_BINDS_PATH", binds_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["msg", str(message_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "ok: true"

def test_msg_unsigned_flag_preserves_bind_sender_without_hash_or_signature(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    message_path = tmp_path / "message.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump(
            [{"Bind": VALID_WALLET_ID, "Domain": "vault.example.com"}],
            sort_keys = False),
        encoding = "utf-8")
    message_path.write_text(
        "To: vault.example.com\nSubject: Echo@Domain\nBody:\n  Ping: pong\n",
        encoding = "utf-8")

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        assert payload["Header"]["From"] == VALID_WALLET_ID
        assert "Hash" not in payload
        assert "Signature" not in payload
        return DummyResponse(b'{"ok":true}')

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(transport_tools, "DEFAULT_BINDS_PATH", binds_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["msg", "--unsigned", str(message_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "ok: true"

def test_msg_anonymous_flag_ignores_stored_bind(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    message_path = tmp_path / "message.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump(
            [{"Bind": VALID_WALLET_ID, "Domain": "vault.example.com"}],
            sort_keys = False),
        encoding = "utf-8")
    message_path.write_text(
        "To: vault.example.com\nSubject: Echo@Domain\nBody:\n  Ping: pong\n",
        encoding = "utf-8")

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        assert payload["Header"]["From"] == "Anonymous"
        assert "Hash" not in payload
        assert "Signature" not in payload
        return DummyResponse(b'{"ok":true}')

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(transport_tools, "DEFAULT_BINDS_PATH", binds_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["msg", "--anonymous", str(message_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "ok: true"

def test_msg_rejects_domain_from_value_for_wallet_send(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    message_path = tmp_path / "message.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    message_path.write_text(
        (
            "Header:\n"
            "  To: vault.example.com\n"
            "  Subject: Custom@Domain\n"
            "  From: sender.example.com\n"
            "Body:\n"
            "  Value: ok\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)

    exit_code = cli.main(["msg", str(message_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert (
        "Wallet-backed commands only support `From: Anonymous` or a UUID bind value."
        in captured.err
    )

def test_msg_reports_missing_message_file(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)

    exit_code = cli.main(["msg", str(tmp_path / "missing.yaml")])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Message file not found" in captured.err

def test_msg_accepts_json_argument(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        assert payload["Header"]["To"] == "vault.example.com"
        assert payload["Header"]["Subject"] == "Echo@Domain"
        assert payload["Body"] == {"Ping": "pong"}
        return DummyResponse(b'{"ok":true}')

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(
        [
            "msg",
            '{"To":"vault.example.com","Subject":"Echo@Domain","Body":{"Ping":"pong"}}',
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "ok: true"

def test_msg_accepts_inline_arguments(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        assert payload["Header"]["To"] == "any-domain.org"
        assert payload["Header"]["Subject"] == "topic@role"
        assert payload["Body"] == {"DynamicBodyProperty": 123}
        return DummyResponse(b"inline")

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(
        [
            "msg",
            "To:any-domain.org",
            "Subject:topic@role",
            "DynamicBodyProperty:123",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "Body: inline"

def test_msg_accepts_inline_headers_without_body(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        assert payload["Header"]["To"] == "any-domain.pollyweb.org"
        assert payload["Header"]["Subject"] == "Echo@Domain"
        assert payload["Body"] == {}
        return DummyResponse(b"headers-only")

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(
        [
            "msg",
            "To:any-domain.dom",
            "Subject:Echo@Domain",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "Body: headers-only"

def test_msg_expands_dom_suffix_from_json_argument(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        assert payload["Header"]["To"] == "any-domain.pollyweb.org"
        assert payload["Header"]["Subject"] == "Echo@Domain"
        assert payload["Body"] == {}
        assert request.full_url == "https://pw.any-domain.pollyweb.org/inbox"
        return DummyResponse(b"expanded-json")

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(
        [
            "msg",
            '{"To":"any-domain.dom","Subject":"Echo@Domain","Body":{}}',
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "Body: expanded-json"

def test_msg_accepts_lowercase_inline_headers_with_debug(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        assert payload["Header"]["To"] == "any-domain.pollyweb.org"
        assert payload["Header"]["Subject"] == "Echo@Domain"
        assert payload["Body"] == {}
        assert request.full_url == "https://pw.any-domain.pollyweb.org/inbox"
        return DummyResponse(b'{"ok":true}')

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(
        [
            "msg",
            "to:any-domain.dom",
            "subject:Echo@Domain",
            "--debug",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Outbound payload to https://pw.any-domain.pollyweb.org/inbox:" in captured.out
    assert "To: any-domain.pollyweb.org" in captured.out
    assert "Subject: Echo@Domain" in captured.out
    assert "Inbound payload:" in captured.out
    assert '{"ok":true}' not in captured.err

def test_msg_accepts_python_message_file(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    message_path = tmp_path / "message.py"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    message_path.write_text(
        (
            "MESSAGE = {\n"
            '    "To": "vault.example.com",\n'
            '    "Subject": "Echo@Domain",\n'
            '    "Body": {"Ping": "pong"},\n'
            "}\n"
        ),
        encoding = "utf-8")

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        assert payload["Header"]["To"] == "vault.example.com"
        assert payload["Header"]["Subject"] == "Echo@Domain"
        assert payload["Body"] == {"Ping": "pong"}
        return DummyResponse(b"python")

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["msg", str(message_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "Body: python"

def test_msg_json_flag_preserves_raw_json_response(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    message_path = tmp_path / "message.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    message_path.write_text(
        "To: vault.example.com\nSubject: Echo@Domain\nBody:\n  Ping: pong\n",
        encoding = "utf-8")

    def fake_urlopen(request):
        return DummyResponse(b'{"ok":true}')

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["msg", "--json", str(message_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == '{"ok":true}'

def test_msg_reports_unresolved_inbox_host(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())

    def fake_urlopen(request):
        raise urllib.error.URLError(
            socket.gaierror(8, "nodename nor servname provided, or not known")
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(
        [
            "msg",
            "To:any-domain.dom",
            "Subject:Echo@Domain",
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert (
        "Could not resolve PollyWeb inbox host pw.any-domain.pollyweb.org"
        in captured.err
    )
