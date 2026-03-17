# Task Plan

- [x] Review the written instructions, docs, and current domain-signing behavior for outbound messages
- [x] Remove `Header.Algorithm` from domain-signed outbound messages at the `pollyweb` library layer
- [x] Add regression coverage proving domain sends/signing omit `Algorithm` while wallet behavior still works
- [x] Update `wallet-cli` only if it assumes `Algorithm` is present on domain messages
- [x] Run targeted verification in both repos and capture the review

# Review

- Updated `/Users/jorgemf/Git/pollyweb-pypi/pollyweb/domain.py` so `Domain.sign()` signs with the DKIM-derived algorithm without serializing `Header.Algorithm` on domain messages.
- Added `/Users/jorgemf/Git/pollyweb-pypi/pollyweb/msg.py` support for detached signing that preserves the exact wire payload while still using the selected algorithm for cryptographic signing.
- Added regression coverage in `/Users/jorgemf/Git/pollyweb-pypi/tests/test_msg.py` to assert domain-signed messages and `Domain.send()` payloads omit `Algorithm`, while verification still succeeds.
- Updated `/Users/jorgemf/Git/pollyweb-pypi/docs/domain/sign.md`, `/Users/jorgemf/Git/pollyweb-pypi/docs/msg.md`, `/Users/jorgemf/Git/pollyweb-pypi/docs/msg/verify.md`, and `/Users/jorgemf/Git/pollyweb-pypi/RELEASES.md` to document the DKIM-inferred behavior.
- Recorded the new rule in `/Users/jorgemf/Git/wallet-cli/AGENTS.md` and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md`; no `wallet-cli` runtime code changes were needed.
- Verified with `cd /Users/jorgemf/Git/pollyweb-pypi && ./.venv/bin/python -m pytest -q tests/test_msg.py` and `cd /Users/jorgemf/Git/wallet-cli && ./.venv/bin/python -m pytest -q tests/test_msg_command.py tests/test_echo.py`.
