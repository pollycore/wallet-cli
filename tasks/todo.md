# Task Plan

- [x] Review the written instructions, docs, and current self-update behavior
- [x] Change the preflight update flow to upgrade automatically instead of prompting or persisting declines
- [x] Update tests and docs to match the automatic upgrade behavior
- [x] Run targeted verification and capture the review

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/cli.py` so the pre-command PyPI check now upgrades automatically whenever it sees a newer published `pollyweb-cli` release, removes the interactive prompt and declined-version file logic, and re-execs the requested command after a successful install.
- Updated `/Users/jorgemf/Git/wallet-cli/tests/test_cli_core.py` and `/Users/jorgemf/Git/wallet-cli/tests/README.md` so the regression coverage now asserts the automatic upgrade path directly, including dev-version upgrade detection and failed-install fallback behavior.
- Updated `/Users/jorgemf/Git/wallet-cli/README.md`, `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md`, and `/Users/jorgemf/Git/wallet-cli/AGENTS.md` so the written behavior consistently says the CLI auto-upgrades instead of asking first or storing declined releases.
- Verified with `./.venv/bin/python -m pytest -q tests/test_cli_core.py` (`25 passed`). The plain `python3 -m pytest -q tests/test_cli_core.py` path was not usable in this workspace because that interpreter does not have `pytest` installed.
