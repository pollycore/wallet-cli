"""Pytest configuration for repository-local imports."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import urllib.request

# Add the repository's package source directory so plain `pytest` can import
# `pollyweb_cli` without requiring an editable install first.
REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_SOURCE = REPO_ROOT / "python"

if str(PYTHON_SOURCE) not in sys.path:
    sys.path.insert(0, str(PYTHON_SOURCE))

from pollyweb_cli import cli
from pollyweb_cli.tools import transport as transport_tools

try:
    import pollyweb.msg as pollyweb_msg
except Exception:  # pragma: no cover - older dependency floors may differ
    pollyweb_msg = None

try:
    import pollyweb._transport as pollyweb_transport
except Exception:  # pragma: no cover - older dependency floors do not expose this
    pollyweb_transport = None


@pytest.fixture(autouse = True)
def skip_upgrade_check(
    monkeypatch,
    request
):
    """Keep CLI self-upgrade preflight out of unit-test command flows."""

    if (
        request.node.name.startswith("test_preflight_")
        or request.node.name.startswith("test_get_latest_published_version_")
        or request.node.name.startswith("test_version_command_checks_for_upgrade_")
        or request.node.name.startswith("test_requires_published_runtime_")
    ):
        return

    env_name = getattr(cli, "SKIP_UPGRADE_CHECK_ENV", None)
    if env_name:
        monkeypatch.setenv(env_name, "1")

    # Most command tests exercise feature behavior rather than the version
    # preflight, so force the normal "skip upgrade" branch even when the local
    # editable/dev runtime would otherwise require a published release.
    monkeypatch.setattr(
        cli,
        "_requires_published_runtime",
        lambda: False,
        raising = False)


@pytest.fixture(autouse = True)
def isolate_profile_paths(
    monkeypatch,
    tmp_path
):
    """Redirect CLI profile state into a per-test temp home directory."""

    fake_home = tmp_path / "home"
    config_dir = fake_home / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_path = config_dir / "config.yaml"
    binds_path = config_dir / "binds.yaml"
    history_dir = config_dir / "history"
    sync_dir = config_dir / "sync"

    config_dir.mkdir(parents = True, exist_ok = True)
    history_dir.mkdir(parents = True, exist_ok = True)
    sync_dir.mkdir(parents = True, exist_ok = True)

    # Keep any code that consults the process home directory away from the
    # real user profile during tests and pre-push runs.
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(cli, "SYNC_DIR", sync_dir)
    monkeypatch.setattr(transport_tools, "DEFAULT_BINDS_PATH", binds_path)


@pytest.fixture(autouse = True)
def bridge_pollyweb_transport_to_cli_urlopen(
    monkeypatch
):
    """Keep existing CLI network stubs working with newer PollyWeb transport."""

    if pollyweb_transport is None:
        return

    def compat_post_json_bytes(
        url: str,
        body: bytes,
        *,
        timeout: float = 10.0
    ) -> bytes:
        """Delegate PollyWeb transport sends through the CLI urlopen stub."""

        request = urllib.request.Request(
            url,
            data = body,
            headers = {"Content-Type": "application/json"},
            method = "POST",
        )

        with cli.urllib.request.urlopen(request) as response:
            return response.read()

    monkeypatch.setattr(
        pollyweb_transport,
        "post_json_bytes",
        compat_post_json_bytes)

    if pollyweb_msg is not None and hasattr(pollyweb_msg, "post_json_bytes"):
        monkeypatch.setattr(
            pollyweb_msg,
            "post_json_bytes",
            compat_post_json_bytes)
