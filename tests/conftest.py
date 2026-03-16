"""Pytest configuration for repository-local imports."""

from __future__ import annotations

import sys
from pathlib import Path


# Add the repository's package source directory so plain `pytest` can import
# `pollyweb_cli` without requiring an editable install first.
REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_SOURCE = REPO_ROOT / "python"

if str(PYTHON_SOURCE) not in sys.path:
    sys.path.insert(0, str(PYTHON_SOURCE))
