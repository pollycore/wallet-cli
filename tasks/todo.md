# Task Plan

- [x] Inspect the wrapped `pw test` fixture loader and execution path for the narrowest `Wait` hook
- [x] Add top-level `Wait` validation and apply the delay before transport
- [x] Add focused regression coverage and verify with the repo test interpreter

# Review

- Added wrapped-fixture `Wait` validation in [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py) so `pw test` accepts a top-level numeric delay next to `Outbound` and `Inbound`, while rejecting non-numeric and negative values with direct fixture errors.
- Applied the `Wait` delay in [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py) immediately before transport, which keeps the existing fixture parsing and wallet send behavior unchanged apart from the requested pause.
- Documented the new wrapped `Wait` field in [/Users/jorgemf/Git/wallet-cli/docs/commands/test.md](/Users/jorgemf/Git/wallet-cli/docs/commands/test.md).
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_test_command.py -k 'wait or accepts_every_checked_in_test_message_fixture'`.
