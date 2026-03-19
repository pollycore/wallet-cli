from __future__ import annotations

import builtins
import json
import socket
import stat
import subprocess
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

def test_bind_sends_unsigned_anonymous_message_and_stores_bind(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    bind_value = f"Bind:{uuid.uuid4()}"
    stored_bind_value = bind_value.split(":", 1)[1]
    requests = []

    def fake_urlopen(request):
        requests.append(request)
        return DummyResponse(bind_value.encode("utf-8"))

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["bind", "vault.example.com"])

    assert exit_code == 0
    assert binds_path.exists()
    assert cli.yaml.safe_load(binds_path.read_text()) == [
        {"Bind": stored_bind_value, "Domain": "vault.example.com"}
    ]
    assert stat.S_IMODE(binds_path.stat().st_mode) == 0o600

    request = requests[0]
    assert request.full_url == "https://pw.vault.example.com/inbox"
    assert request.get_method() == "POST"
    assert request.headers["Content-type"] == "application/json"
    body = request.data.decode()
    assert '"From":"Anonymous"' in body
    assert '"Schema":"pollyweb.org/MSG:1.0"' in body
    assert '"To":"vault.example.com"' in body
    assert '"Subject":"Bind@Vault"' in body
    assert '"Domain":"vault.example.com"' in body
    assert "-----BEGIN PUBLIC KEY-----" not in body
    assert "-----END PUBLIC KEY-----" not in body
    assert '\\n' not in body.split('"PublicKey":"', 1)[1].split('"', 1)[0]
    assert '"Hash":"' not in body
    assert '"Signature":"' not in body

    captured = capsys.readouterr()
    assert stored_bind_value in captured.out
    assert str(binds_path) in captured.out

def test_bind_normalizes_dom_alias_when_using_wallet_send(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    bind_value = f"Bind:{uuid.uuid4()}"
    stored_bind_value = bind_value.split(":", 1)[1]
    requests = []

    def fake_urlopen(request):
        requests.append(request)
        return DummyResponse(bind_value.encode("utf-8"))

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["bind", "any-hoster.dom"])

    assert exit_code == 0
    assert cli.yaml.safe_load(binds_path.read_text()) == [
        {"Bind": stored_bind_value, "Domain": "any-hoster.pollyweb.org"}
    ]

    request = requests[0]
    assert request.full_url == "https://pw.any-hoster.pollyweb.org/inbox"
    body = request.data.decode()
    assert '"To":"any-hoster.pollyweb.org"' in body
    assert '"Schema":"pollyweb.org/MSG:1.0"' in body
    assert '"Domain":"any-hoster.pollyweb.org"' in body

    captured = capsys.readouterr()
    assert "Stored bind for any-hoster.dom" in captured.out

def test_bind_anonymous_flag_ignores_stored_bind(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump(
            [{"Bind": VALID_WALLET_ID, "Domain": "vault.example.com"}],
            sort_keys = False),
        encoding = "utf-8")

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        assert payload["Header"]["From"] == "Anonymous"
        assert "Hash" not in payload
        assert "Signature" not in payload
        return DummyResponse(VALID_BIND.encode("utf-8"))

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["bind", "--anonymous", "vault.example.com"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Stored bind for vault.example.com" in captured.out


def test_bind_logs_created_bind_entry(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    log_path = config_dir / "binds.log"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    bind_value = f"Bind:{uuid.uuid4()}"
    stored_bind_value = bind_value.split(":", 1)[1]

    def fake_urlopen(request):
        return DummyResponse(bind_value.encode("utf-8"))

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["bind", "any-hoster.pollyweb.org"])

    assert exit_code == 0
    assert log_path.exists()
    log_text = log_path.read_text(encoding = "utf-8")
    assert "created bind for any-hoster.pollyweb.org" in log_text
    assert f"new_bind: {stored_bind_value}" in log_text
    assert stat.S_IMODE(log_path.stat().st_mode) == 0o600
    capsys.readouterr()


def test_bind_noop_save_skips_binds_write_and_audit_log(tmp_path):
    config_dir = tmp_path / ".pollyweb"
    binds_path = config_dir / "binds.yaml"
    log_path = config_dir / "binds.log"
    config_dir.mkdir()
    bind_value = str(uuid.uuid4())
    binds_path.write_text(
        cli.yaml.safe_dump(
            [{"Bind": bind_value, "Domain": "any-hoster.pollyweb.org"}],
            sort_keys = False),
        encoding = "utf-8")
    original_yaml = binds_path.read_text(encoding = "utf-8")

    cli.save_bind(
        {"Bind": bind_value},
        "any-hoster.dom",
        binds_path)

    assert binds_path.read_text(encoding = "utf-8") == original_yaml
    assert not log_path.exists()


def test_bind_logs_alert_when_replacing_domain_entry(tmp_path):
    config_dir = tmp_path / ".pollyweb"
    binds_path = config_dir / "binds.yaml"
    log_path = config_dir / "binds.log"
    config_dir.mkdir()
    previous_bind = str(uuid.uuid4())
    next_bind = str(uuid.uuid4())
    binds_path.write_text(
        cli.yaml.safe_dump(
            [{"Bind": previous_bind, "Domain": "any-hoster.pollyweb.org"}],
            sort_keys = False),
        encoding = "utf-8")

    with pytest.raises(cli.UserFacingError):
        cli.save_bind(
            {"Bind": next_bind},
            "any-hoster.pollyweb.org",
            binds_path)

    log_text = log_path.read_text(encoding = "utf-8")
    assert "ALERT bind changed for any-hoster.pollyweb.org" in log_text
    assert "script_path:" in log_text
    assert f"previous_bind: {previous_bind}" in log_text
    assert f"new_bind: {next_bind}" in log_text


def test_bind_raises_alert_when_same_domain_bind_changes(monkeypatch, tmp_path):
    config_dir = tmp_path / ".pollyweb"
    binds_path = config_dir / "binds.yaml"
    log_path = config_dir / "binds.log"
    config_dir.mkdir()
    previous_bind = str(uuid.uuid4())
    next_bind = str(uuid.uuid4())
    binds_path.write_text(
        cli.yaml.safe_dump(
            [{"Bind": previous_bind, "Domain": "any-hoster.pollyweb.org"}],
            sort_keys = False),
        encoding = "utf-8")
    notifications = []

    def fake_run(command, check, stdout, stderr):
        notifications.append((command, check, stdout, stderr))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(cli.bind_feature.subprocess, "run", fake_run)
    monkeypatch.setattr(cli.bind_feature.sys, "argv", ["/tmp/fake-runner.py"])
    monkeypatch.setattr(cli.bind_feature, "get_bind_change_version", lambda: "9.9.9")
    expected_script_path = str(Path("/tmp/fake-runner.py").resolve())

    with pytest.raises(cli.UserFacingError) as excinfo:
        cli.save_bind(
            {"Bind": next_bind},
            "any-hoster.pollyweb.org",
            binds_path)

    assert "Bind changed unexpectedly for any-hoster.pollyweb.org." in str(excinfo.value)
    assert "The local bind was not updated" in str(excinfo.value)
    assert f"Script path: {expected_script_path}" in str(excinfo.value)
    assert "Version: 9.9.9" in str(excinfo.value)
    assert cli.yaml.safe_load(binds_path.read_text(encoding = "utf-8")) == [
        {"Bind": previous_bind, "Domain": "any-hoster.pollyweb.org"}
    ]
    log_text = log_path.read_text(encoding = "utf-8")
    assert "ALERT bind changed for any-hoster.pollyweb.org" in log_text
    assert f"script_path: {expected_script_path}" in log_text
    assert "version: 9.9.9" in log_text
    assert f"previous_bind: {previous_bind}" in log_text
    assert f"new_bind: {next_bind}" in log_text
    assert notifications
    assert notifications[0][0][0] == "osascript"


def test_bind_change_alert_skips_os_notification_during_pytest(
    monkeypatch,
    tmp_path
):
    config_dir = tmp_path / ".pollyweb"
    binds_path = config_dir / "binds.yaml"
    log_path = config_dir / "binds.log"
    config_dir.mkdir()
    previous_bind = str(uuid.uuid4())
    next_bind = str(uuid.uuid4())
    binds_path.write_text(
        cli.yaml.safe_dump(
            [{"Bind": previous_bind, "Domain": "any-hoster.pollyweb.org"}],
            sort_keys = False),
        encoding = "utf-8")
    notifications = []

    def fake_run(command, check, stdout, stderr):
        notifications.append((command, check, stdout, stderr))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(cli.bind_feature.subprocess, "run", fake_run)
    monkeypatch.setattr(
        cli.bind_feature,
        "PYTEST_CURRENT_TEST_ENV",
        "PW_FAKE_PYTEST_CURRENT_TEST")
    monkeypatch.setenv("PW_FAKE_PYTEST_CURRENT_TEST", "tests/test_bind.py::test")

    with pytest.raises(cli.UserFacingError):
        cli.save_bind(
            {"Bind": next_bind},
            "any-hoster.pollyweb.org",
            binds_path)

    log_text = log_path.read_text(encoding = "utf-8")
    assert "ALERT bind changed for any-hoster.pollyweb.org" in log_text
    assert notifications == []

def test_serialize_public_key_value_strips_pem_wrappers():
    pem = (
        "-----BEGIN PUBLIC KEY-----\n"
        "MCowBQYDK2VwAyEA1234567890abcdefghijklmnopqrstuv==\n"
        "-----END PUBLIC KEY-----\n"
    )

    assert (
        cli.serialize_public_key_value(pem)
        == "MCowBQYDK2VwAyEA1234567890abcdefghijklmnopqrstuv=="
    )

def test_bind_debug_prints_outbound_and_inbound_payloads(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    bind_value = f"Bind:{uuid.uuid4()}"

    def fake_urlopen(request):
        return DummyResponse(bind_value.encode("utf-8"))

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["bind", "--debug", "vault.example.com"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "\nOutbound payload to https://pw.vault.example.com/inbox:\n" in captured.out
    assert "Outbound payload to https://pw.vault.example.com/inbox:" in captured.out
    assert "Subject: Bind@Vault" in captured.out
    assert "To: vault.example.com" in captured.out
    assert "From: Anonymous" in captured.out
    assert "Schema: pollyweb.org/MSG:1.0" in captured.out
    assert "Domain: vault.example.com" in captured.out
    outbound = captured.out.split("\n\nInbound payload:\n", 1)[0]
    assert "Hash:" not in outbound
    assert "Signature:" not in outbound
    assert "\n\nInbound payload:\n" in captured.out
    assert "Inbound payload:" in captured.out
    assert "Body:" in captured.out
    assert bind_value in captured.out
    assert captured.err == ""

def test_bind_appends_without_overwriting_existing_binds(monkeypatch, tmp_path):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump([{"Bind": "existing", "Domain": "old.example.com"}]),
    )
    bind_value = f"Bind:{uuid.uuid4()}"
    stored_bind_value = bind_value.split(":", 1)[1]

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(
        cli.urllib.request, "urlopen", lambda request: DummyResponse(bind_value.encode())
    )

    exit_code = cli.main(["bind", "vault.example.com"])

    assert exit_code == 0
    assert cli.yaml.safe_load(binds_path.read_text()) == [
        {"Bind": "existing", "Domain": "old.example.com"},
        {"Bind": stored_bind_value, "Domain": "vault.example.com"},
    ]

def test_bind_rejects_existing_bind_for_same_domain(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    bind_value = f"Bind:{uuid.uuid4()}"
    binds_path.write_text(
        cli.yaml.safe_dump([{"Bind": "existing", "Domain": "vault.example.com"}]),
    )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(
        cli.urllib.request, "urlopen", lambda request: DummyResponse(bind_value.encode())
    )
    monkeypatch.setattr(
        cli.bind_feature.subprocess,
        "run",
        lambda command, check, stdout, stderr: subprocess.CompletedProcess(command, 0),
    )

    exit_code = cli.main(["bind", "vault.example.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Bind changed unexpectedly for vault.example.com." in captured.err
    assert cli.yaml.safe_load(binds_path.read_text()) == [
        {"Bind": "existing", "Domain": "vault.example.com"}
    ]

def test_bind_keeps_distinct_schema_entries_for_same_domain(monkeypatch, tmp_path):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    bind_value = f"Bind:{uuid.uuid4()}"
    stored_bind_value = bind_value.split(":", 1)[1]
    binds_path.write_text(
        cli.yaml.safe_dump(
            [
                {
                    "Bind": "existing",
                    "Domain": "vault.example.com",
                    "Schema": "schema:one",
                }
            ]
        ),
    )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(
        cli.urllib.request,
        "urlopen",
        lambda request: DummyResponse(
            cli.json.dumps({"Bind": bind_value, "Schema": "schema:two"}).encode()
        ),
    )

    exit_code = cli.main(["bind", "vault.example.com"])

    assert exit_code == 0
    assert cli.yaml.safe_load(binds_path.read_text()) == [
        {
            "Bind": "existing",
            "Domain": "vault.example.com",
            "Schema": "schema:one",
        },
        {
            "Bind": stored_bind_value,
            "Schema": "schema:two",
            "Domain": "vault.example.com",
        },
    ]

def test_bind_rejects_existing_bind_with_matching_schema(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    bind_value = f"Bind:{uuid.uuid4()}"
    binds_path.write_text(
        cli.yaml.safe_dump(
            [
                {
                    "Bind": "existing",
                    "Domain": "vault.example.com",
                    "Schema": "schema:one",
                }
            ]
        ),
    )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(
        cli.urllib.request,
        "urlopen",
        lambda request: DummyResponse(
            cli.json.dumps({"Bind": bind_value, "Schema": "schema:one"}).encode()
        ),
    )

    exit_code = cli.main(["bind", "vault.example.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Bind changed unexpectedly for vault.example.com." in captured.err
    assert cli.yaml.safe_load(binds_path.read_text()) == [
        {
            "Bind": "existing",
            "Domain": "vault.example.com",
            "Schema": "schema:one",
        }
    ]

def test_bind_requires_existing_keys(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)

    exit_code = cli.main(["bind", "vault.example.com"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Run `pw config` first" in captured.err

    captured = capsys.readouterr()
    assert captured.out == ""

def test_bind_requires_bind_token_in_response(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(
        cli.urllib.request, "urlopen", lambda request: DummyResponse(b'{"ok":true}')
    )

    exit_code = cli.main(["bind", "vault.example.com"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Could not bind vault.example.com." in captured.err
    assert "did not include a bind token" in captured.err


def test_bind_accepts_json_bind_value_without_prefix(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    bind_uuid = str(uuid.uuid4())

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(
        cli.urllib.request,
        "urlopen",
        lambda request: DummyResponse(
            cli.json.dumps({"Bind": bind_uuid}).encode("utf-8")
        ),
    )

    exit_code = cli.main(["bind", "any-hoster.pollyweb.org"])

    assert exit_code == 0
    assert cli.yaml.safe_load(binds_path.read_text()) == [
        {"Bind": bind_uuid, "Domain": "any-hoster.pollyweb.org"}
    ]
    captured = capsys.readouterr()
    assert f"Stored bind for any-hoster.pollyweb.org: {bind_uuid}" in captured.out


def test_bind_reports_unresolved_inbox_host(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
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
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["bind", "any-host.dom"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert (
        "Could not resolve PollyWeb inbox host pw.any-host.pollyweb.org"
        in captured.err
    )
