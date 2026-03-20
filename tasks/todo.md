# Task Plan

- [x] Inspect the current `pw test` fixture-label and spinner behavior in code and tests
- [x] Update the spinner text to include the folder-aware fixture name
- [x] Add focused regression coverage for single-file and directory-sweep spinner labels
- [x] Verify with the repo test interpreter and record the outcome here

# Review

- Updated [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py) so the `pw test` send spinner now uses the same folder-aware fixture display name as the concise pass/fail output, rendering labels like `Testing message: nested/fixture`.
- Added [/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py](/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py) assertions for spinner labels on single-file runs, default directory sweeps, and nested fixtures so the progress text stays aligned with the displayed fixture path.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_test_command.py`.
