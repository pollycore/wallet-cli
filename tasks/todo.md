# Task Plan

- [x] Review the written instructions, docs, and current wallet-backed send behavior
- [x] Add shared `--unsigned` and `--anonymous` handling for wallet-backed CLI send paths
- [x] Extend the `pollyweb` transport rules so unsigned UUID-backed sends are valid
- [x] Cover bind, msg, shell, sync, chat, and shared parser behavior with regression tests
- [x] Refresh command docs and record the lesson after verification
- [x] Run targeted verification in both `wallet-cli` and `pollyweb-pypi`

# Review

- Added `--unsigned` and `--anonymous` to `pw msg`, `bind`, `test`, `shell`, `chat`, `sync`, and `echo`.
- `--anonymous` now bypasses stored bind lookup and forces `From: Anonymous`; for `pw chat` it also switches the subscription channel and auth token body to `Anonymous`.
- `--unsigned` now strips `Hash` and `Signature` while keeping the selected sender, including stored bind UUID senders.
- Updated `pollyweb` so direct unsigned UUID-backed `Msg.send()` calls validate and transport cleanly.
- Refreshed README, command docs, AGENTS guidance, lessons, and verification coverage for the new flags.
- Verified with `./.venv/bin/python -m pytest -q tests/test_cli.py -k 'test_bind_ or test_msg_ or test_test_ or test_echo_ or test_shell_ or test_sync_ or test_chat_'` and `./.venv/bin/python -m pytest -q tests/test_msg.py -k 'TestWallet or unsigned'`.
