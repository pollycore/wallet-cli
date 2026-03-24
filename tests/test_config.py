from __future__ import annotations

import stat

from pollyweb_cli import cli
from pollyweb_cli.features import config as config_feature

def test_config_creates_keypair_files(monkeypatch, tmp_path, capsys):
    """config creates the local wallet files and an empty config object."""

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
    assert private_key_path.exists()
    assert public_key_path.exists()
    assert config_path.exists()
    assert private_key_path.read_text().startswith("-----BEGIN PRIVATE KEY-----")
    assert public_key_path.read_text().startswith("-----BEGIN PUBLIC KEY-----")
    assert cli.yaml.safe_load(config_path.read_text()) == {}

    captured = capsys.readouterr()
    assert str(private_key_path) in captured.out
    assert str(public_key_path) in captured.out
    assert str(config_path) in captured.out

def test_config_is_idempotent_when_keys_already_exist(monkeypatch, tmp_path, capsys):
    """config reuses a complete existing profile without rewriting it."""

    config_dir = tmp_path / ".pollyweb"
    config_dir.mkdir()
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"
    private_key_path.write_text("existing-private")
    public_key_path.write_text("existing-public")
    config_path.write_text("{}")
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)

    exit_code = cli.main(["config"])

    assert exit_code == 0
    assert private_key_path.read_text() == "existing-private"
    assert public_key_path.read_text() == "existing-public"
    assert config_path.read_text() == "{}"

    captured = capsys.readouterr()
    assert str(private_key_path) in captured.out
    assert str(public_key_path) in captured.out
    assert str(config_path) in captured.out
    assert captured.err == ""

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

    exit_code = cli.main(["config", "--force"])

    assert exit_code == 0
    assert private_key_path.read_text() != "existing-private"
    assert public_key_path.read_text() != "existing-public"
    assert cli.yaml.safe_load(config_path.read_text()) == {}

def test_config_sets_expected_permissions(monkeypatch, tmp_path):
    """config applies the expected filesystem permissions."""

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
