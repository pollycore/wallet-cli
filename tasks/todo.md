# Task Plan

- [x] Inspect the current `pw test` array subset matcher and confirm why wildcard placeholders inside arrays fall back to raw list equality
- [x] Update `pw test` inbound array validation so placeholder-bearing items act as repeated templates for all matching array entries
- [x] Add focused regression coverage and verify with the repo test interpreter

# Review

- Updated [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py) so `pw test` now treats array items that contain `"<str>"`, `"<int>"`, or `"<uuid>"` as wildcard templates, while array items without placeholders must still exist as exact subset matches somewhere in the response array.
- The array matcher now validates mixed arrays by first matching the fixed expected items anywhere in the actual array, then requiring every remaining actual item to satisfy one of the wildcard template items.
- Added [/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py](/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py) coverage for the reported `Domains` shape, including the success case where the fixed item appears in the middle and the failure case where an extra array entry does not satisfy the `"<str>"` template.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_test_command.py` (`47 passed, 1 skipped`).
