from __future__ import annotations

import builtins
import json
import stat
import uuid
import urllib.error
from pathlib import Path

import pollyweb.msg as pollyweb_msg
import pytest

from pollyweb import Msg
from pollyweb_cli import cli
from pollyweb_cli.features import chat as chat_feature

VALID_BIND = "Bind:123e4567-e89b-12d3-a456-426614174000"
VALID_WALLET_ID = "123e4567-e89b-12d3-a456-426614174000"


class DummyResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def make_echo_response_payload(
    *,
    from_value: str,
    correlation: str,
    private_key,
    selector: str = "default",
    body: dict[str, object] | None = None,
) -> bytes:
    # Build and sign the echo response using the pollyweb Msg class.
    # To mirrors From — the server echoes back to whoever sent the request.
    msg = Msg(
        From=from_value,
        To=from_value,
        Subject="Echo@Domain",
        Correlation=correlation,
        Selector=selector,
        Body=body or {"Echo": "ok"},
    ).sign(private_key)

    return json.dumps(msg.to_dict()).encode("utf-8")


class FakeReadline:
    def __init__(self):
        self.history: list[str] = []
        self.history_length = None

    def clear_history(self):
        self.history.clear()

    def add_history(self, item: str):
        self.history.append(item)

    def set_history_length(self, length: int):
        self.history_length = length


class FakeChatConnection:
    def __init__(self, notifier_domain: str, wallet_id: str, auth_token: str):
        self.notifier_domain = notifier_domain
        self.wallet_id = wallet_id
        self.auth_token = auth_token
        self.calls: list[str] = []

    def connect(self) -> None:
        self.calls.append("connect")

    def subscribe(self) -> None:
        self.calls.append("subscribe")

    def listen_forever(self) -> None:
        self.calls.append("listen")
        raise KeyboardInterrupt()

    def close(self) -> None:
        self.calls.append("close")


def test_version_flag_prints_installed_version(monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_installed_version", lambda _: "1.2.3")

    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])

    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "pw 1.2.3"
    assert captured.err == ""


def test_parser_includes_chat_command():
    parser = cli.build_parser()

    args = parser.parse_args(["chat"])

    assert args.command == "chat"


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
    assert message.Body["Wallet"] == VALID_WALLET_ID
    assert message.verify(key_pair.PublicKey) is True


def test_chat_exit_payload_stops_listener(capsys):
    should_stop = chat_feature._print_event_payload(
        {"event": ["EXIT"]})

    assert should_stop is True
    captured = capsys.readouterr()
    assert "Received EXIT. Stopping chat listener." in captured.out


def test_chat_requires_wallet_in_config(tmp_path):
    config_dir = tmp_path / ".pollyweb"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text("Helpers:\n  Notifier: any-notifier.pollyweb.org\n", encoding = "utf-8")

    with pytest.raises(cli.UserFacingError):
        chat_feature.load_wallet_id(config_path)


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
        "Helpers": {"Notifier": "any-notifier.pollyweb.org"}
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
    config_path.write_text("Helpers:\n  Notifier: any-notifier.pollyweb.org\n")
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)

    exit_code = cli.main(["config"])

    assert exit_code == 0
    assert private_key_path.read_text() == "existing-private"
    assert public_key_path.read_text() == "existing-public"
    assert config_path.read_text() == "Helpers:\n  Notifier: any-notifier.pollyweb.org\n"

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
        "Helpers": {"Notifier": "any-notifier.pollyweb.org"}
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
    assert '"Schema":' not in body
    assert '"To":"vault.example.com"' in body
    assert '"Subject":"Bind@Vault"' in body
    assert "-----BEGIN PUBLIC KEY-----" not in body
    assert "-----END PUBLIC KEY-----" not in body
    assert '\\n' not in body.split('"PublicKey":"', 1)[1].split('"', 1)[0]
    assert '"Hash":"' in body
    assert '"Signature":"' in body

    captured = capsys.readouterr()
    assert bind_value in captured.out
    assert str(binds_path) in captured.out


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
    assert "Schema:" not in captured.out
    assert "\n\nInbound payload:\n" in captured.out
    assert "Inbound payload:" in captured.out
    assert "Body:" in captured.out
    assert bind_value in captured.out
    assert captured.err == ""


def test_print_debug_payload_wraps_long_unbroken_strings_as_literal_blocks(capsys):
    cli.print_debug_payload(
        "Outbound payload",
        {
            "Body": {"PublicKey": "A" * 96},
            "Signature": "B" * 96,
        },
    )

    captured = capsys.readouterr()
    assert "PublicKey: |" in captured.out
    assert "Signature: |" in captured.out
    assert "A" * 64 in captured.out
    assert "A" * 32 in captured.out
    assert "B" * 64 in captured.out
    assert "B" * 32 in captured.out


def test_print_debug_payload_wraps_public_key_even_when_shorter_than_width(capsys):
    cli.print_debug_payload(
        "Outbound payload",
        {
            "Body": {
                "PublicKey": "MCowBQYDK2VwAyEA1234567890abcdefghijklmnopqrstuv=="
            }
        },
    )

    captured = capsys.readouterr()
    assert "PublicKey: |" in captured.out
    assert "MCowBQYDK2VwAyEA1234567890abcdefghijklmnopqrstuv==" in captured.out


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


def test_bind_replaces_existing_bind_for_same_domain(monkeypatch, tmp_path):
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
        cli.yaml.safe_dump([{"Bind": "Bind:existing", "Domain": "vault.example.com"}]),
    )

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
        {"Bind": bind_value, "Domain": "vault.example.com"}
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
    binds_path.write_text(
        cli.yaml.safe_dump(
            [
                {
                    "Bind": "Bind:existing",
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
            "Bind": "Bind:existing",
            "Domain": "vault.example.com",
            "Schema": "schema:one",
        },
        {
            "Bind": bind_value,
            "Schema": "schema:two",
            "Domain": "vault.example.com",
        },
    ]


def test_bind_replaces_existing_bind_with_matching_schema(monkeypatch, tmp_path):
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
                    "Bind": "Bind:existing",
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

    assert exit_code == 0
    assert cli.yaml.safe_load(binds_path.read_text()) == [
        {
            "Bind": bind_value,
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


def test_main_renders_user_facing_errors_in_red(monkeypatch):
    monkeypatch.setattr(cli.sys.stderr, "isatty", lambda: True)
    monkeypatch.setattr(cli, "cmd_echo", lambda domain, debug: (_ for _ in ()).throw(cli.UserFacingError("boom")))
    printed = []

    def fake_print(*args, **kwargs):
        printed.append((args, kwargs))

    monkeypatch.setattr(builtins, "print", fake_print)

    exit_code = cli.main(["echo", "vault.example.com"])

    assert exit_code == 1
    assert printed == [
        (
            (f"{cli.ERROR_STYLE}Error: boom{cli.ERROR_STYLE_RESET}",),
            {"file": cli.sys.stderr},
        )
    ]


def test_main_renders_bind_errors_in_red(monkeypatch):
    monkeypatch.setattr(cli.sys.stderr, "isatty", lambda: True)
    monkeypatch.setattr(
        cli,
        "cmd_bind",
        lambda domain, debug: (_ for _ in ()).throw(
            cli.UserFacingError(
                f"Could not bind {domain}. The server returned HTTP 500."
            )
        ),
    )
    printed = []

    def fake_print(*args, **kwargs):
        printed.append((args, kwargs))

    monkeypatch.setattr(builtins, "print", fake_print)

    exit_code = cli.main(["bind", "any-hoster.pollyweb.org"])

    assert exit_code == 1
    assert printed == [
        (
            (
                f"{cli.ERROR_STYLE}Error: Could not bind any-hoster.pollyweb.org. "
                f"The server returned HTTP 500.{cli.ERROR_STYLE_RESET}",
            ),
            {"file": cli.sys.stderr},
        )
    ]


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


def test_print_echo_response_formats_payload(capsys):
    cli.print_echo_response(
        '{"Header":{"Subject":"Echo@Domain"},"Body":{"Echo":"ok"}}'
    )

    captured = capsys.readouterr()
    assert "\nEcho response:\n" in captured.out
    assert "Subject: Echo@Domain" in captured.out
    assert "Echo: ok" in captured.out


def test_shell_debug_prints_outbound_and_inbound_payloads(
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
        cli.yaml.safe_dump([{"Bind": VALID_BIND, "Domain": "vault.example.com"}]),
    )

    def fake_urlopen(request):
        return DummyResponse(b'{"ok":true}')

    commands = iter(["status --json target=prod", EOFError()])

    def fake_input(prompt):
        result = next(commands)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(builtins, "input", fake_input)

    exit_code = cli.main(["shell", "--debug", "vault.example.com"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "\nOutbound payload to https://pw.vault.example.com/inbox:\n" in captured.out
    assert "Outbound payload to https://pw.vault.example.com/inbox:" in captured.out
    assert "Subject: Shell@Domain" in captured.out
    assert "From: 123e4567-e89b-12d3-a456-426614174000" in captured.out
    assert "Command: status" in captured.out
    assert "Arguments:" in captured.out
    assert "json: target=prod" in captured.out
    assert "Binds:" not in captured.out
    assert "\n\nInbound payload:\n" in captured.out
    assert "Inbound payload:" in captured.out
    assert "ok: true" in captured.out
    assert captured.err == ""


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
    assert len(requests) == 3
    init_body = requests[0].data.decode("utf-8")
    first_body = requests[1].data.decode("utf-8")
    second_body = requests[2].data.decode("utf-8")
    assert '"Subject":"Shell@Domain"' in init_body
    assert '"From":"123e4567-e89b-12d3-a456-426614174000"' in init_body
    assert '"Command":"help"' in init_body
    assert '"Arguments":{}' in init_body
    assert '"Binds":' not in init_body
    assert '"Subject":"Shell@Domain"' in first_body
    assert '"From":"123e4567-e89b-12d3-a456-426614174000"' in first_body
    assert '"Command":"balance"' in first_body
    assert '"Arguments":{}' in first_body
    assert '"Binds":' not in first_body
    assert '"Command":"send"' in second_body
    assert '"Arguments":{"0":"10","1":"alice"}' in second_body
    assert '"From":"123e4567-e89b-12d3-a456-426614174000"' in second_body

    captured = capsys.readouterr()
    assert captured.out == "ok:2\nok:3\n\n"
    assert captured.err == ""


def test_print_shell_response_colors_success_codes(monkeypatch):
    printed = []

    class FakeConsole:
        def print(self, payload, style=None):
            printed.append((payload, style))

    monkeypatch.setattr(cli, "SHELL_CONSOLE", FakeConsole())

    cli.print_shell_response('{"Code":200,"Message":"ok"}')

    assert len(printed) == 1
    rendered, style = printed[0]
    assert isinstance(rendered, cli.Markdown)
    assert style == "green"


def test_print_shell_response_colors_error_codes(monkeypatch):
    printed = []

    class FakeConsole:
        def print(self, payload, style=None):
            printed.append((payload, style))

    monkeypatch.setattr(cli, "SHELL_CONSOLE", FakeConsole())

    cli.print_shell_response('{"Code":"503","Message":"down"}')

    assert len(printed) == 1
    rendered, style = printed[0]
    assert isinstance(rendered, cli.Markdown)
    assert style == "bold red"


def test_print_shell_response_renders_string_body_as_markdown(monkeypatch):
    printed = []

    class FakeConsole:
        def print(self, payload, style=None):
            printed.append((payload, style))

    monkeypatch.setattr(cli, "SHELL_CONSOLE", FakeConsole())

    cli.print_shell_response('{"Code":200,"Body":"# Hello\\n\\n- item"}')

    assert len(printed) == 1
    rendered, style = printed[0]
    assert isinstance(rendered, cli.Markdown)
    assert style == "green"


def test_print_shell_response_renders_string_message_as_markdown(monkeypatch):
    printed = []

    class FakeConsole:
        def print(self, payload, style=None):
            printed.append((payload, style))

    monkeypatch.setattr(cli, "SHELL_CONSOLE", FakeConsole())

    cli.print_shell_response('{"Code":404,"Message":"# Missing\\n\\n- help"}')

    assert len(printed) == 1
    rendered, style = printed[0]
    assert isinstance(rendered, cli.Markdown)
    assert style == "yellow"


def test_print_shell_response_prints_raw_payload_when_body_is_not_a_string(
    monkeypatch, capsys
):
    class FakeConsole:
        def print(self, payload, style=None):
            raise AssertionError("console rendering should not be used")

    monkeypatch.setattr(cli, "SHELL_CONSOLE", FakeConsole())

    cli.print_shell_response('{"Body":{"ok":true}}')

    captured = capsys.readouterr()
    assert captured.out == '{"Body":{"ok":true}}\n'


def test_print_shell_response_falls_back_to_plain_print_for_non_http_payloads(
    monkeypatch, capsys
):
    class FakeConsole:
        def print(self, payload, style=None):
            raise AssertionError("console rendering should not be used")

    monkeypatch.setattr(cli, "SHELL_CONSOLE", FakeConsole())

    cli.print_shell_response("ok:1")
    cli.print_shell_response('{"Other":"data"}')

    captured = capsys.readouterr()
    assert captured.out == 'ok:1\n{"Other":"data"}\n'


def test_parse_shell_command_splits_command_and_arguments():
    assert cli.parse_shell_command("balance") == ("balance", [])
    assert cli.parse_shell_command('send --amount 10 user=alice "two words"') == (
        "send",
        ["--amount", "10", "user=alice", "two words"],
    )


def test_get_shell_from_value_strips_bind_prefix():
    assert (
        cli.get_shell_from_value("Bind:123e4567-e89b-12d3-a456-426614174000")
        == "123e4567-e89b-12d3-a456-426614174000"
    )
    assert cli.get_shell_from_value("existing") == "existing"


def test_build_shell_arguments_maps_long_flag_to_dictionary_entry():
    assert cli.build_shell_arguments(["--all", "123"]) == {"all": "123"}


def test_build_shell_arguments_maps_short_flag_to_dictionary_entry():
    assert cli.build_shell_arguments(["-a", "123"]) == {"a": "123"}


def test_build_shell_arguments_maps_equals_token_to_dictionary_entry():
    assert cli.build_shell_arguments(["a=123"]) == {"a": "123"}


def test_build_shell_arguments_keeps_positional_arguments_indexed():
    assert cli.build_shell_arguments(["10", "alice"]) == {
        "0": "10",
        "1": "alice",
    }


def test_parse_shell_command_rejects_invalid_quoting():
    try:
        cli.parse_shell_command('"unterminated')
    except cli.UserFacingError as exc:
        assert "Invalid shell command" in str(exc)
    else:
        raise AssertionError("Expected UserFacingError for invalid shell command")


def test_is_shell_exit_command_matches_supported_aliases():
    for command in [
        "exit",
        "quit",
        "!q",
        "!quit",
        "!qa",
        "!qall",
        "!wq",
        "!x",
        "!quit!",
    ]:
        assert cli.is_shell_exit_command(command) is True

    assert cli.is_shell_exit_command("balance") is False
    assert cli.is_shell_exit_command("!status") is False


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
    binds_path.write_text(
        cli.yaml.safe_dump([{"Bind": VALID_BIND, "Domain": "vault.example.com"}]),
        encoding="utf-8",
    )
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
    assert len(requests) == 1
    init_body = requests[0].data.decode("utf-8")
    assert '"Command":"help"' in init_body
    assert '"Arguments":{}' in init_body
    captured = capsys.readouterr()
    assert captured.out == "\n"
    assert captured.err == ""


def test_shell_exits_without_sending_user_command_for_exit_aliases(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    history_dir = config_dir / "history"
    history_path = history_dir / "vault.example.com.txt"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump([{"Bind": VALID_BIND, "Domain": "vault.example.com"}]),
        encoding="utf-8",
    )
    user_inputs = iter(["!q"])
    requests = []

    def fake_input(_prompt):
        value = next(user_inputs)
        if isinstance(value, BaseException):
            raise value
        return value

    def fake_urlopen(request):
        requests.append(request)
        return DummyResponse(b"ok")

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["shell", "vault.example.com"])

    assert exit_code == 0
    assert len(requests) == 1
    assert '"Command":"help"' in requests[0].data.decode("utf-8")
    assert not history_path.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
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
    binds_path.write_text(
        cli.yaml.safe_dump([{"Bind": VALID_BIND, "Domain": "vault.example.com"}]),
        encoding="utf-8",
    )
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


def test_shell_requires_bind_for_target_domain(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump([{"Bind": "Bind:other", "Domain": "other.example.com"}]),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)

    exit_code = cli.main(["shell", "vault.example.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "No bind stored for vault.example.com." in captured.err
    assert "Run `pw bind vault.example.com` first." in captured.err


def test_shell_loads_and_updates_domain_history(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    history_dir = config_dir / "history"
    history_path = history_dir / "vault.example.com.txt"
    config_dir.mkdir()
    history_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump([{"Bind": VALID_BIND, "Domain": "vault.example.com"}]),
        encoding="utf-8",
    )
    history_path.write_text("older balance\nolder send bob\n", encoding="utf-8")
    fake_readline = FakeReadline()
    user_inputs = iter(["fresh status", EOFError()])

    def fake_input(_prompt):
        value = next(user_inputs)
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(cli, "readline", fake_readline)
    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(
        cli.urllib.request, "urlopen", lambda request: DummyResponse(b"ok")
    )

    exit_code = cli.main(["shell", "vault.example.com"])

    assert exit_code == 0
    assert fake_readline.history_length == cli.SHELL_HISTORY_LIMIT
    assert fake_readline.history == [
        "older balance",
        "older send bob",
        "fresh status",
    ]
    assert history_path.read_text(encoding="utf-8") == (
        "older balance\nolder send bob\nfresh status\n"
    )
    captured = capsys.readouterr()
    assert captured.out == "ok\n\n"


def test_shell_history_is_scoped_per_domain_and_trimmed_to_last_twenty(monkeypatch, tmp_path):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    history_dir = config_dir / "history"
    config_dir.mkdir()
    history_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump([{"Bind": VALID_BIND, "Domain": "vault.example.com"}]),
        encoding="utf-8",
    )
    vault_history_path = history_dir / "vault.example.com.txt"
    other_history_path = history_dir / "other.example.com.txt"
    vault_history_path.write_text(
        "\n".join(f"cmd-{index}" for index in range(19)) + "\n",
        encoding="utf-8",
    )
    other_history_path.write_text("other-cmd\n", encoding="utf-8")
    fake_readline = FakeReadline()
    user_inputs = iter(["cmd-19", "cmd-20", EOFError()])

    def fake_input(_prompt):
        value = next(user_inputs)
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(cli, "readline", fake_readline)
    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(
        cli.urllib.request, "urlopen", lambda request: DummyResponse(b"ok")
    )

    exit_code = cli.main(["shell", "vault.example.com"])

    assert exit_code == 0
    assert vault_history_path.read_text(encoding="utf-8").splitlines() == [
        *(f"cmd-{index}" for index in range(1, 19)),
        "cmd-19",
        "cmd-20",
    ]
    assert other_history_path.read_text(encoding="utf-8") == "other-cmd\n"


# --- sync tests ---


def _setup_sync_env(monkeypatch, tmp_path):
    """Set up config dir with keys and a bind for vault.example.com."""
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    sync_dir = config_dir / "sync"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump([{"Bind": VALID_BIND, "Domain": "vault.example.com"}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli, "SYNC_DIR", sync_dir)
    return config_dir, sync_dir


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


# --- Onboard@Notifier tests ---


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
    assert "Hash" in body
    assert "Signature" in body

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
    assert "Hash:" in captured.out
    assert "Signature:" in captured.out
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
            "Notifier": "any-notifier.pollyweb.org",
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
        "Helpers": {"Notifier": "any-notifier.pollyweb.org"}
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
