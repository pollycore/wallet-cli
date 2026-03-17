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

def test_build_sync_files_map_returns_sha1_hashes(tmp_path, monkeypatch):
    sync_dir = tmp_path / "sync"
    domain_dir = sync_dir / "vault.example.com"
    domain_dir.mkdir(parents=True)
    (domain_dir / "file.txt").write_bytes(b"hello")
    sub = domain_dir / "sub"
    sub.mkdir()
    (sub / "data.yaml").write_bytes(b"key: value")
    monkeypatch.setattr(cli, "SYNC_DIR", sync_dir)

    result = cli.build_sync_files_map("vault.example.com")

    # Use cli.build_sync_files_map output directly; verify keys are present and non-empty
    assert set(result.keys()) == {"/file.txt", "/sub/data.yaml"}
    assert len(result["/file.txt"]["Hash"]) == 40
    assert len(result["/sub/data.yaml"]["Hash"]) == 40

def test_build_sync_files_map_raises_when_directory_missing(tmp_path, monkeypatch):
    sync_dir = tmp_path / "sync"
    sync_dir.mkdir()
    monkeypatch.setattr(cli, "SYNC_DIR", sync_dir)

    try:
        cli.build_sync_files_map("vault.example.com")
    except cli.UserFacingError as exc:
        assert "does not exist" in str(exc)
    else:
        raise AssertionError("Expected UserFacingError for missing sync directory")

def test_sync_sends_map_filer_message_with_correct_body(monkeypatch, tmp_path, capsys):
    config_dir, sync_dir = _setup_sync_env(monkeypatch, tmp_path)
    domain_dir = sync_dir / "vault.example.com"
    domain_dir.mkdir(parents=True)
    content = b"hello world"
    (domain_dir / "index.html").write_bytes(content)

    requests = []

    def fake_urlopen(request):
        requests.append(request)
        return DummyResponse(
            cli.json.dumps({"Map": "map-uuid-123", "Files": {"/index.html": {"Action": "UPLOAD"}}}).encode()
        )

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["sync", "vault.example.com"])

    assert exit_code == 0
    assert len(requests) == 1
    request = requests[0]
    assert request.full_url == "https://pw.vault.example.com/inbox"
    assert request.get_method() == "POST"

    body = cli.json.loads(request.data.decode("utf-8"))
    assert body["Header"]["Subject"] == "Map@Filer"
    assert body["Header"]["To"] == "vault.example.com"
    assert body["Header"]["From"] == "123e4567-e89b-12d3-a456-426614174000"

    # Verify the file hash is a non-empty SHA1 hex string (40 chars)
    assert len(body["Body"]["Files"]["/index.html"]["Hash"]) == 40

    captured = capsys.readouterr()
    assert "Map: map-uuid-123" in captured.out
    assert "UPLOAD: /index.html" in captured.out

def test_sync_prints_all_file_actions(monkeypatch, tmp_path, capsys):
    config_dir, sync_dir = _setup_sync_env(monkeypatch, tmp_path)
    domain_dir = sync_dir / "vault.example.com"
    domain_dir.mkdir(parents=True)
    (domain_dir / "a.txt").write_bytes(b"a")
    (domain_dir / "b.txt").write_bytes(b"b")

    response_body = cli.json.dumps({
        "Map": "map-abc",
        "Files": {
            "/a.txt": {"Action": "UPLOAD"},
            "/b.txt": {"Action": "REMOVE"},
        },
    }).encode()

    monkeypatch.setattr(
        cli.urllib.request, "urlopen", lambda r: DummyResponse(response_body)
    )

    exit_code = cli.main(["sync", "vault.example.com"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Map: map-abc" in captured.out
    assert "UPLOAD: /a.txt" in captured.out
    assert "REMOVE: /b.txt" in captured.out

def test_sync_requires_bind_for_domain(monkeypatch, tmp_path, capsys):
    config_dir, sync_dir = _setup_sync_env(monkeypatch, tmp_path)

    exit_code = cli.main(["sync", "other.example.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "No bind stored for other.example.com" in captured.err

def test_sync_anonymous_flag_skips_bind_requirement(monkeypatch, tmp_path, capsys):
    config_dir, sync_dir = _setup_sync_env(monkeypatch, tmp_path)
    domain_dir = sync_dir / "other.example.com"
    domain_dir.mkdir(parents=True)
    (domain_dir / "f.txt").write_bytes(b"data")
    requests = []

    def fake_urlopen(request):
        requests.append(cli.json.loads(request.data.decode("utf-8")))
        return DummyResponse(
            cli.json.dumps({"Map": "map-anon", "Files": {"/f.txt": {"Action": "UPLOAD"}}}).encode()
        )

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["sync", "--anonymous", "other.example.com"])

    assert exit_code == 0
    assert requests[0]["Header"]["From"] == "Anonymous"
    captured = capsys.readouterr()
    assert "Map: map-anon" in captured.out

def test_sync_unsigned_flag_removes_hash_and_signature(
    monkeypatch, tmp_path, capsys
):
    config_dir, sync_dir = _setup_sync_env(monkeypatch, tmp_path)
    domain_dir = sync_dir / "vault.example.com"
    domain_dir.mkdir(parents=True)
    (domain_dir / "f.txt").write_bytes(b"data")
    requests = []

    def fake_urlopen(request):
        requests.append(cli.json.loads(request.data.decode("utf-8")))
        return DummyResponse(
            cli.json.dumps({"Map": "map-unsigned", "Files": {"/f.txt": {"Action": "UPLOAD"}}}).encode()
        )

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["sync", "--unsigned", "vault.example.com"])

    assert exit_code == 0
    assert requests[0]["Header"]["From"] == VALID_WALLET_ID
    assert "Hash" not in requests[0]
    assert "Signature" not in requests[0]
    captured = capsys.readouterr()
    assert "Map: map-unsigned" in captured.out

def test_sync_requires_configured_keys(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    config_dir.mkdir()
    sync_dir = config_dir / "sync"
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", config_dir / "private.pem")
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", config_dir / "public.pem")
    monkeypatch.setattr(cli, "BINDS_PATH", config_dir / "binds.yaml")
    monkeypatch.setattr(cli, "SYNC_DIR", sync_dir)

    exit_code = cli.main(["sync", "vault.example.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "pw config" in captured.err

def test_sync_raises_user_error_when_sync_dir_missing(monkeypatch, tmp_path, capsys):
    config_dir, sync_dir = _setup_sync_env(monkeypatch, tmp_path)
    # sync_dir exists but no domain subdirectory

    exit_code = cli.main(["sync", "vault.example.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "does not exist" in captured.err

def test_sync_handles_http_error(monkeypatch, tmp_path, capsys):
    config_dir, sync_dir = _setup_sync_env(monkeypatch, tmp_path)
    domain_dir = sync_dir / "vault.example.com"
    domain_dir.mkdir(parents=True)
    (domain_dir / "f.txt").write_bytes(b"data")

    def fake_urlopen(_request):
        raise urllib.error.HTTPError(None, 503, "Service Unavailable", {}, None)

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["sync", "vault.example.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Sync request to vault.example.com failed with HTTP 503" in captured.err

def test_sync_handles_url_error(monkeypatch, tmp_path, capsys):
    config_dir, sync_dir = _setup_sync_env(monkeypatch, tmp_path)
    domain_dir = sync_dir / "vault.example.com"
    domain_dir.mkdir(parents=True)
    (domain_dir / "f.txt").write_bytes(b"data")

    def fake_urlopen(_request):
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["sync", "vault.example.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Sync request to vault.example.com failed: timed out" in captured.err

def test_sync_debug_prints_outbound_and_inbound_payloads(monkeypatch, tmp_path, capsys):
    config_dir, sync_dir = _setup_sync_env(monkeypatch, tmp_path)
    domain_dir = sync_dir / "vault.example.com"
    domain_dir.mkdir(parents=True)
    (domain_dir / "f.txt").write_bytes(b"data")

    monkeypatch.setattr(
        cli.urllib.request,
        "urlopen",
        lambda r: DummyResponse(
            cli.json.dumps({"Map": "m1", "Files": {}}).encode()
        ),
    )

    exit_code = cli.main(["sync", "--debug", "vault.example.com"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Outbound payload to https://pw.vault.example.com/inbox:" in captured.out
    assert "Subject: Map@Filer" in captured.out
    assert "Inbound payload:" in captured.out

