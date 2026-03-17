# Task Plan

- [x] Inspect the existing `pw bind` error handling and related docs/tests
- [x] Add a human-readable network error message for unresolved bind inbox hosts
- [x] Cover the new bind error behavior with tests
- [x] Run targeted verification for the bind tests
- [x] Capture the result and learning in project notes

# Review

- Added a bind-specific DNS error formatter so `pw bind` no longer exposes raw `socket.gaierror` text.
- Added regression coverage for unresolved inbox hosts during `pw bind`.
- Verified with `./.venv/bin/python -m pytest -q tests/test_cli.py -k 'bind_reports_unresolved_inbox_host or msg_reports_unresolved_inbox_host or bind_requires_bind_token_in_response or bind_sends_signed_message_and_stores_bind'`.
