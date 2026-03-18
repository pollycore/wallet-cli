# Task Plan

- [x] Review the written instructions, docs, and current `pw test` placeholder behavior
- [x] Add `"<PublicKey>"` fixture resolution for outbound `pw test` payloads using the wallet public key in `~/.pollyweb/public.pem`
- [x] Add regression coverage for public-key placeholder expansion and the missing-key error path
- [x] Update docs and repo guidance for the new `pw test` placeholder
- [x] Run targeted verification and capture the review

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py` so wrapped `pw test` fixtures now resolve the exact string `"<PublicKey>"` from `/Users/jorgemf/.pollyweb/public.pem` before sending, using the same PEM-stripping serializer as `pw bind` while preserving the existing `{BindOf(domain)}` placeholder behavior.
- Added regression coverage in `/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py` for both successful public-key expansion and the user-facing error when the wallet public key is missing.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/test.md`, `/Users/jorgemf/Git/wallet-cli/README.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so the written behavior documents the new placeholder and the maintenance guidance captures the shared-serializer requirement.
- Verified with `./.venv/bin/python -m pip install -e '.[dev]'` to refresh the editable install used by the local venv, then `./.venv/bin/python -m pytest -q tests/test_test_command.py` (`12 passed, 1 skipped`).
