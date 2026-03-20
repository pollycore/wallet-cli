# Task Plan

- [x] Inspect the `pw test` parallel runner, spinner behavior, and failure reporting paths
- [x] Replace flat parallel status with a hierarchical progress view for folder groups, file groups, and active fixtures
- [x] Keep immediate pass output during nested parallel runs and preserve exact nested fixture names on failure
- [x] Add focused regression coverage and verify with the repo test interpreter
- [x] Fix the local concurrency regression by moving hierarchical status rendering off worker threads

# Review

- Updated [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py) so non-debug parallel `pw test` runs execute nested folder and file batches in-process, which lets one shared Rich status render a hierarchical tree of active folder groups, file groups, and leaf fixtures.
- Kept immediate success feedback by printing each `✅ Passed: ...` line as soon as its fixture completes, even when sibling folders and sibling files are still running in parallel.
- Tightened parallel failure propagation in [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py) so the reported failure name stays pinned to the concrete nested fixture path instead of collapsing back to only the parent folder group.
- Added regression coverage in [/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py](/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py) for hierarchical status rendering, immediate nested success output, parallel same-prefix file groups, parallel same-prefix folder groups, and nested fixture-path failure reporting.
- Followed up on the local `Bad file descriptor` regression by moving the shared hierarchical status lifecycle onto a dedicated renderer thread in [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py), so worker threads only publish state changes and never touch Rich console handles directly.
- Finalized the renderer lifecycle in [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py) so resolved success and failure rows render once, retire cleanly, and let the shared status thread shut down without leaking into later `pw test` runs.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_test_command.py`.
