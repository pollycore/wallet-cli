from __future__ import annotations

import builtins
import stat
import uuid
import urllib.error

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

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)

    exit_code = cli.main(["config"])

    assert exit_code == 0
    assert private_key_path.exists()
    assert public_key_path.exists()
    assert private_key_path.read_text().startswith("-----BEGIN PRIVATE KEY-----")
    assert public_key_path.read_text().startswith("-----BEGIN PUBLIC KEY-----")

    captured = capsys.readouterr()
    assert str(private_key_path) in captured.out
    assert str(public_key_path) in captured.out


def test_config_is_idempotent_when_keys_already_exist(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    config_dir.mkdir()
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    private_key_path.write_text("existing-private")
    public_key_path.write_text("existing-public")
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)

    exit_code = cli.main(["config"])

    assert exit_code == 0
    assert private_key_path.read_text() == "existing-private"
    assert public_key_path.read_text() == "existing-public"

    captured = capsys.readouterr()
    assert str(private_key_path) in captured.out
    assert str(public_key_path) in captured.out
    assert captured.err == ""


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
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)

    exit_code = cli.main(["config", "--force"])

    assert exit_code == 0
    assert private_key_path.read_text() != "existing-private"
    assert public_key_path.read_text() != "existing-public"


def test_config_sets_expected_permissions(monkeypatch, tmp_path):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)

    exit_code = cli.main(["config"])

    assert exit_code == 0
    assert stat.S_IMODE(private_key_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(public_key_path.stat().st_mode) == 0o644


def test_bind_sends_signed_message_and_stores_bind(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    bind_value = f"Bind:{uuid.uuid4()}"
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
        {"Bind": bind_value, "Domain": "vault.example.com"}
    ]
    assert stat.S_IMODE(binds_path.stat().st_mode) == 0o600

    request = requests[0]
    assert request.full_url == "https://pw.vault.example.com/inbox"
    assert request.get_method() == "POST"
    assert request.headers["Content-type"] == "application/json"
    body = request.data.decode()
    assert '"From":"Anonymous"' in body
    assert '"To":"vault.example.com"' in body
    assert '"Subject":"Bind@Vault"' in body
    assert '"PublicKey":"-----BEGIN PUBLIC KEY-----\\n' in body
    assert '"Hash":"' in body
    assert '"Signature":"' in body

    captured = capsys.readouterr()
    assert bind_value in captured.out
    assert str(binds_path) in captured.out


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
        cli.yaml.safe_dump([{"Bind": "Bind:existing", "Domain": "old.example.com"}]),
    )
    bind_value = f"Bind:{uuid.uuid4()}"

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
        {"Bind": "Bind:existing", "Domain": "old.example.com"},
        {"Bind": bind_value, "Domain": "vault.example.com"},
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
    assert "Bind:<UUID>" in captured.err
    assert 'Response preview: {"ok":true}' in captured.err


def test_shell_sends_signed_messages_until_eof(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds = [
        {"Bind": "Bind:123e4567-e89b-12d3-a456-426614174000", "Domain": "vault.example.com"}
    ]
    binds_path.write_text(cli.yaml.safe_dump(binds), encoding="utf-8")
    requests = []
    prompts = []
    user_inputs = iter(["balance", "send 10 alice", EOFError()])

    def fake_input(prompt):
        prompts.append(prompt)
        value = next(user_inputs)
        if isinstance(value, BaseException):
            raise value
        return value

    def fake_urlopen(request):
        requests.append(request)
        return DummyResponse(f"ok:{len(requests)}".encode("utf-8"))

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["shell", "vault.example.com"])

    assert exit_code == 0
    assert prompts == [
        "pw:vault.example.com> ",
        "pw:vault.example.com> ",
        "pw:vault.example.com> ",
    ]
    assert len(requests) == 2
    first_body = requests[0].data.decode("utf-8")
    second_body = requests[1].data.decode("utf-8")
    assert '"Subject":"Shell@Domain"' in first_body
    assert '"Command":"balance"' in first_body
    assert '"Binds":[{"Bind":"Bind:123e4567-e89b-12d3-a456-426614174000","Domain":"vault.example.com"}]' in first_body
    assert '"Command":"send 10 alice"' in second_body

    captured = capsys.readouterr()
    assert captured.out == "ok:1\nok:2\n\n"
    assert captured.err == ""


def test_shell_ignores_blank_commands_and_exits_on_keyboard_interrupt(
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
    binds_path.write_text("[]", encoding="utf-8")
    user_inputs = iter(["   ", KeyboardInterrupt()])
    requests = []

    def fake_input(_prompt):
        value = next(user_inputs)
        if isinstance(value, BaseException):
            raise value
        return value

    def fake_urlopen(request):
        requests.append(request)
        return DummyResponse(b"unexpected")

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["shell", "vault.example.com"])

    assert exit_code == 0
    assert requests == []
    captured = capsys.readouterr()
    assert captured.out == "\n"
    assert captured.err == ""


def test_shell_stops_on_request_error(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds_path.write_text("[]", encoding="utf-8")
    user_inputs = iter(["balance"])

    def fake_input(_prompt):
        value = next(user_inputs)
        if isinstance(value, BaseException):
            raise value
        return value

    def fake_urlopen(_request):
        raise urllib.error.URLError("connection dropped")

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["shell", "vault.example.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Shell request to vault.example.com failed: connection dropped" in captured.err
