# Task Plan

- [x] Inspect the `pw test` fixture sweep behavior, spinner/output expectations, and current ordering rules
- [x] Group same-folder fixtures by leading numeric prefix and run matching groups in parallel for non-debug batch runs
- [x] Keep debug and single-fixture behavior sequential, and preserve deterministic output ordering
- [x] Add focused regression coverage and verify with the repo test interpreter

# Review

- Updated [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py) so batch `pw test` runs now group same-folder fixtures whose filenames share a leading numeric prefix like `03-` and execute each group in parallel when `--debug` is off, while still printing success lines in the original sorted order.
- Kept debug behavior sequential in [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py), and refactored one-fixture execution to return its concise success line so the batch runner can control ordered output cleanly.
- Extended [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py) so same-prefix sibling subfolders also batch in parallel under non-debug directory sweeps, using the same deterministic ordering and subprocess isolation as same-folder YAML file groups.
- Added regression coverage in [/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py](/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py) for parallel same-prefix file batches, parallel same-prefix subfolder batches, and the `--debug` sequential fallback, and documented the batching rule in [/Users/jorgemf/Git/wallet-cli/tasks/lessons.md](/Users/jorgemf/Git/wallet-cli/tasks/lessons.md).
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_test_command.py`.
