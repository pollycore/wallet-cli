# Task Plan

- [x] Inspect the current `pw chat` transport, docs, and reusable `pw echo` terminal UI patterns
- [x] Implement a terminal chat app for `pw chat` while preserving the AppSync auth and channel behavior
- [x] Add focused regression coverage for the new interactive chat path and keep the plain fallback behavior working
- [x] Verify with the repo test interpreter and record the outcome here

# Review

- Updated [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/chat.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/chat.py) so `pw chat` now opens a Textual chat UI in interactive terminals, with a Rich header, a live transcript, an input box, `/quit` support, and a single worker thread that owns the AppSync websocket for both publish and receive traffic.
- Kept the existing non-interactive behavior as a fallback: when `pw chat` is not running on a TTY, it still prints connection status and streams events line-by-line, including the current `--debug`, `--test`, and `--anonymous` semantics.
- Added [/Users/jorgemf/Git/wallet-cli/tests/test_chat.py](/Users/jorgemf/Git/wallet-cli/tests/test_chat.py) coverage for timestamped transcript formatting and for the interactive command path opening the Textual app and returning its exit code.
- Updated [/Users/jorgemf/Git/wallet-cli/docs/commands/chat.md](/Users/jorgemf/Git/wallet-cli/docs/commands/chat.md) to describe the new interactive chat app and the plain-output fallback.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_chat.py` and `./.venv-tests/bin/python -m pytest -q tests/test_cli_core.py -k chat`.
