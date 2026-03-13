from __future__ import annotations

import stat
from pathlib import Path

from pollyweb_cli import cli


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


def test_config_refuses_to_overwrite_existing_keys(monkeypatch, tmp_path, capsys):
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

    assert exit_code == 1
    assert private_key_path.read_text() == "existing-private"
    assert public_key_path.read_text() == "existing-public"

    captured = capsys.readouterr()
    assert "already exist" in captured.err


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
