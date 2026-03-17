# Task Plan

- [x] Review the written instructions, docs, and current version command behavior
- [x] Replace the `pw --version` flag with a `pw version` subcommand in the CLI parser and dispatch
- [x] Update tests and docs to match the new command shape
- [x] Run targeted verification and capture the review

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/parser.py` and `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/cli.py` so the CLI now reports its installed release through `pw version` instead of a top-level `--version` flag, while keeping the same preflight upgrade check and `pw <version>` output format.
- Updated `/Users/jorgemf/Git/wallet-cli/tests/test_cli_core.py` and `/Users/jorgemf/Git/wallet-cli/tests/conftest.py` so the regression coverage exercises `cli.main(["version"])` and still proves the upgrade preflight runs before printing the installed version.
- Updated `/Users/jorgemf/Git/wallet-cli/README.md`, `/Users/jorgemf/Git/wallet-cli/docs/usage.md`, `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md`, and `/Users/jorgemf/Git/wallet-cli/AGENTS.md` so the written instructions consistently refer to `pw version`.
- Verified with `./.venv/bin/python -m pytest -q tests/test_cli_core.py` and `./.venv/bin/python -m pollyweb_cli.cli version`, which printed `pw 0.1.dev43`.
