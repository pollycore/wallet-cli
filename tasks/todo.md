# Task Plan

- [x] Remove `pw sync` from parser registration, CLI dispatch, and feature imports
- [x] Delete the `sync` feature module and related docs/test scaffolding
- [x] Add focused coverage for the updated command surface and verify in `./.venv-tests`

# Review

- Removed the `pw sync` command from the public CLI surface by deleting its parser registration and dispatch/wrapper code in [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/parser.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/parser.py) and [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/cli.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/cli.py).
- Deleted the obsolete feature implementation and command-specific documentation at [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/sync.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/sync.py) and [/Users/jorgemf/Git/wallet-cli/docs/commands/sync.md](/Users/jorgemf/Git/wallet-cli/docs/commands/sync.md), and scrubbed the usage/test indexes that still referenced them.
- Removed sync-only test scaffolding, deleted [/Users/jorgemf/Git/wallet-cli/tests/test_sync.py](/Users/jorgemf/Git/wallet-cli/tests/test_sync.py), and added a parser regression check in [/Users/jorgemf/Git/wallet-cli/tests/test_cli_core.py](/Users/jorgemf/Git/wallet-cli/tests/test_cli_core.py) to confirm `sync` is no longer an accepted subcommand.
- Verified with `./.venv-tests/bin/python -m pytest` (`235 passed, 1 skipped`).
