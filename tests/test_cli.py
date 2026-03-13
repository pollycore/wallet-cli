from __future__ import annotations

import stat

from pollyweb_cli import cli


class DummyResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_config_creates_keypair_files(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    requests = []

    def fake_urlopen(request):
        requests.append(request)
        return DummyResponse(b'{"Wallet":"wallet-123"}')

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["config"])

    assert exit_code == 0
    assert private_key_path.exists()
    assert public_key_path.exists()
    assert private_key_path.read_text().startswith("-----BEGIN PRIVATE KEY-----")
    assert public_key_path.read_text().startswith("-----BEGIN PUBLIC KEY-----")

    captured = capsys.readouterr()
    assert str(private_key_path) in captured.out
    assert str(public_key_path) in captured.out
    assert "Wallet: wallet-123" in captured.out
    assert len(requests) == 1
    request = requests[0]
    assert request.full_url == "https://pw.any-notifier.pollyweb.org/inbox"
    assert request.get_method() == "POST"
    assert request.headers["Content-type"] == "application/json"
    body = request.data.decode()
    assert '"From":"Anonymous"' in body
    assert '"To":"any-notifier.pollyweb.org"' in body
    assert '"Subject":"Onboard@Notifier"' in body
    assert '"Language":"en-us"' in body
    assert '"PublicKey":"' in body


def test_config_is_idempotent_when_keys_already_exist(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    config_dir.mkdir()
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    private_key_path.write_text("existing-private")
    public_key_path.write_text("existing-public")
    requests = []

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", lambda request: requests.append(request))

    exit_code = cli.main(["config"])

    assert exit_code == 0
    assert private_key_path.read_text() == "existing-private"
    assert public_key_path.read_text() == "existing-public"

    captured = capsys.readouterr()
    assert str(private_key_path) in captured.out
    assert str(public_key_path) in captured.out
    assert captured.err == ""
    assert requests == []


def test_config_refuses_partial_configuration_without_force(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    config_dir.mkdir()
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    private_key_path.write_text("existing-private")

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)

    exit_code = cli.main(["config"])

    assert exit_code == 1
    assert private_key_path.read_text() == "existing-private"
    assert not public_key_path.exists()

    captured = capsys.readouterr()
    assert "partially configured" in captured.err


def test_config_force_overwrites_existing_keys(monkeypatch, tmp_path):
    config_dir = tmp_path / ".pollyweb"
    config_dir.mkdir()
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    private_key_path.write_text("existing-private")
    public_key_path.write_text("existing-public")
    requests = []

    def fake_urlopen(request):
        requests.append(request)
        return DummyResponse(b'{"Wallet":"wallet-456"}')

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["config", "--force"])

    assert exit_code == 0
    assert private_key_path.read_text() != "existing-private"
    assert public_key_path.read_text() != "existing-public"
    assert len(requests) == 1


def test_config_sets_expected_permissions(monkeypatch, tmp_path):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(
        cli.urllib.request,
        "urlopen",
        lambda request: DummyResponse(b'{"Wallet":"wallet-789"}'),
    )

    exit_code = cli.main(["config"])

    assert exit_code == 0
    assert stat.S_IMODE(private_key_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(public_key_path.stat().st_mode) == 0o644


def test_send_onboard_message_requires_json_object(monkeypatch):
    monkeypatch.setattr(
        cli.urllib.request,
        "urlopen",
        lambda request: DummyResponse(b'["not","a","dict"]'),
    )

    try:
        cli.send_onboard_message(b"PUBLIC")
    except ValueError as exc:
        assert "JSON object" in str(exc)
    else:
        raise AssertionError("Expected ValueError for non-object response")
