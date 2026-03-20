# Task Plan

- [x] Inspect the existing `pw test` timeout handling, docs, and worktree state before editing
- [x] Add timeout-aware `pw test` failure reporting with elapsed/client timeout details
- [x] Cover timeout reporting with targeted automated tests
- [x] Update `pw test` docs and review notes for the new timeout output

# Review

- Added timeout-aware `pw test` failure wording in [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py) so timeout-shaped transport errors now report the configured client timeout, measured send duration, missing server timing, and any fixture `Wait` separately.
- Updated wallet transport timing capture in [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/tools/transport.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/tools/transport.py) so failed sends populate timeout-related timing data the test command can explain.
- Documented the new timeout behavior in [/Users/jorgemf/Git/wallet-cli/docs/commands/test.md](/Users/jorgemf/Git/wallet-cli/docs/commands/test.md) and added focused regression coverage in [/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py](/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py).
