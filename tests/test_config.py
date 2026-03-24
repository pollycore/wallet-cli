from __future__ import annotations

import json
import stat
import urllib.error

from pollyweb_cli import cli
from pollyweb_cli.features import config as config_feature

from tests.cli_test_helpers import VALID_WALLET_ID


def _install_fake_onboard(
    monkeypatch,
    *,
    wallet_id: str = VALID_WALLET_ID,
    notifier_domain: str = "any-notifier.pollyweb.org"
) -> list[dict[str, object]]:
    """Stub notifier onboarding and capture the outbound request."""

    calls: list[dict[str, object]] = []

    def fake_send_wallet_message(
        domain,
        subject,
        body,
        key_pair,
        **kwargs
    ):
        """Return one wrapped notifier onboarding response."""

        calls.append(
            {
                "domain": domain,
                "subject": subject,
                "body": body,
                "kwargs": kwargs,
                "key_pair": key_pair,
            }
        )
        response_payload = {
            "Response": {
                "Broker": "any-broker.pollyweb.org",
                "Wallet": wallet_id,
            }
        }
        return json.dumps(response_payload), object(), notifier_domain

    monkeypatch.setattr(
        config_feature,
        "send_wallet_message",
        fake_send_wallet_message)

    return calls


def test_config_creates_keypair_files_and_registers_wallet(monkeypatch, tmp_path, capsys):
    """config creates the wallet files and persists notifier onboarding details."""

    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"

    onboard_calls = _install_fake_onboard(monkeypatch)

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)

    exit_code = cli.main(["config"])

    assert exit_code == 0
    assert private_key_path.exists()
    assert public_key_path.exists()
    assert config_path.exists()
    assert private_key_path.read_text().startswith("-----BEGIN PRIVATE KEY-----")
    assert public_key_path.read_text().startswith("-----BEGIN PUBLIC KEY-----")
    assert cli.yaml.safe_load(config_path.read_text()) == {
        "Helpers": {
            "Notifier": "any-notifier.pollyweb.org",
        },
        "Wallet": VALID_WALLET_ID,
    }
    assert onboard_calls[0]["domain"] == "any-notifier.pollyweb.org"
    assert onboard_calls[0]["subject"] == "Onboard@Notifier"
    assert onboard_calls[0]["body"]["PublicKey"]

    captured = capsys.readouterr()
    assert str(private_key_path) in captured.out
    assert str(public_key_path) in captured.out
    assert str(config_path) in captured.out
    assert "✅ Registered with Notifier: any-notifier.pollyweb.org" in captured.out


def test_config_rechecks_existing_wallet_registration_idempotently(monkeypatch, tmp_path, capsys):
    """config reuses a complete profile and expects the same wallet id back."""

    config_dir = tmp_path / ".pollyweb"
    config_dir.mkdir()
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    config_path.write_text(
        "Helpers:\n"
        "  Notifier: any-notifier.pollyweb.org\n"
        f"Wallet: {VALID_WALLET_ID}\n",
        encoding = "utf-8")

    onboard_calls = _install_fake_onboard(monkeypatch)

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)

    exit_code = cli.main(["config"])

    assert exit_code == 0
    assert len(onboard_calls) == 1
    assert cli.yaml.safe_load(config_path.read_text()) == {
        "Helpers": {
            "Notifier": "any-notifier.pollyweb.org",
        },
        "Wallet": VALID_WALLET_ID,
    }

    captured = capsys.readouterr()
    assert str(private_key_path) in captured.out
    assert str(public_key_path) in captured.out
    assert str(config_path) in captured.out
    assert "✅ Registered with Notifier: any-notifier.pollyweb.org" in captured.out
    assert captured.err == ""


def test_config_raises_drift_error_when_notifier_returns_different_wallet(monkeypatch, tmp_path, capsys):
    """config fails when a repeated notifier onboard returns a different wallet id."""

    config_dir = tmp_path / ".pollyweb"
    config_dir.mkdir()
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    config_path.write_text(
        "Helpers:\n"
        "  Notifier: any-notifier.pollyweb.org\n"
        "Wallet: 00000000-0000-0000-0000-000000000000\n",
        encoding = "utf-8")

    _install_fake_onboard(monkeypatch, wallet_id = VALID_WALLET_ID)

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)

    exit_code = cli.main(["config"])

    assert exit_code == 1
    assert "Wallet registration drift detected." in capsys.readouterr().err
    assert cli.yaml.safe_load(config_path.read_text())["Wallet"] == (
        "00000000-0000-0000-0000-000000000000"
    )


def test_config_surfaces_http_onboard_failures_as_user_errors(monkeypatch, tmp_path, capsys):
    """config renders notifier HTTP failures as a normal command error."""

    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"

    def fake_send_wallet_message(*args, **kwargs):
        """Raise one wrapped notifier HTTP failure."""

        error = urllib.error.HTTPError(
            url = "https://pw.any-notifier.pollyweb.org/inbox",
            code = 502,
            msg = "Bad Gateway",
            hdrs = None,
            fp = None)
        setattr(error, "pollyweb_error_body", '{"error":"Notifier upstream failed"}')
        raise error

    monkeypatch.setattr(
        config_feature,
        "send_wallet_message",
        fake_send_wallet_message)
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)

    exit_code = cli.main(["config"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert (
        "Could not register this wallet with the Notifier. "
        "The notifier returned HTTP 502 Bad Gateway. Notifier upstream failed"
    ) in captured.err


def test_config_debug_shows_full_http_error_body(monkeypatch, tmp_path, capsys):
    """config --debug includes the raw notifier error body when one exists."""

    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"

    def fake_send_wallet_message(*args, **kwargs):
        """Raise one wrapped notifier HTTP failure."""

        error = urllib.error.HTTPError(
            url = "https://pw.any-notifier.pollyweb.org/inbox",
            code = 502,
            msg = "Bad Gateway",
            hdrs = None,
            fp = None)
        setattr(
            error,
            "pollyweb_error_body",
            '{"error":"Notifier upstream failed","details":{"trace":"abc123"}}')
        raise error

    monkeypatch.setattr(
        config_feature,
        "send_wallet_message",
        fake_send_wallet_message)
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)

    exit_code = cli.main(["config", "--debug"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Full error body:" in captured.err
    assert '{"error":"Notifier upstream failed","details":{"trace":"abc123"}}' in captured.err


def test_config_refuses_partial_configuration_without_force(monkeypatch, tmp_path, capsys):
    """config refuses partial profiles unless --force is supplied."""

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
    """config --force replaces keys and rewrites the config file from onboarding."""

    config_dir = tmp_path / ".pollyweb"
    config_dir.mkdir()
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"
    private_key_path.write_text("existing-private")
    public_key_path.write_text("existing-public")
    config_path.write_text("Helpers:\n  Notifier: old.example.com\n", encoding = "utf-8")

    _install_fake_onboard(
        monkeypatch,
        notifier_domain = "old.example.com")

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)

    exit_code = cli.main(["config", "--force"])

    assert exit_code == 0
    assert private_key_path.read_text() != "existing-private"
    assert public_key_path.read_text() != "existing-public"
    assert cli.yaml.safe_load(config_path.read_text()) == {
        "Helpers": {
            "Notifier": "old.example.com",
        },
        "Wallet": VALID_WALLET_ID,
    }


def test_config_sets_expected_permissions(monkeypatch, tmp_path):
    """config applies the expected filesystem permissions."""

    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"

    _install_fake_onboard(monkeypatch)

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)

    exit_code = cli.main(["config"])

    assert exit_code == 0
    assert stat.S_IMODE(private_key_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(public_key_path.stat().st_mode) == 0o644
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600


def test_load_notifier_domain_prefers_configured_helper(tmp_path):
    """chat helper lookup still honors Helpers.Notifier when present."""

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "Helpers:\n"
        "  Notifier: notifier.example.com\n",
        encoding = "utf-8")

    assert config_feature.load_notifier_domain(config_path) == "notifier.example.com"


def test_load_notifier_domain_falls_back_to_default_when_missing(tmp_path):
    """chat helper lookup falls back to the default notifier domain."""

    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}", encoding = "utf-8")

    assert config_feature.load_notifier_domain(config_path) == "any-notifier.pollyweb.org"
