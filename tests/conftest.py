"""Pytest configuration for repository-local imports."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add the repository's package source directory so plain `pytest` can import
# `pollyweb_cli` without requiring an editable install first.
REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_SOURCE = REPO_ROOT / "python"

if str(PYTHON_SOURCE) not in sys.path:
    sys.path.insert(0, str(PYTHON_SOURCE))

from pollyweb_cli import cli


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
        lambda: False)
