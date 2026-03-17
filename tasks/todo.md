# Task Plan

- [x] Review the written instructions, docs, and current `pw echo` validation behavior
- [x] Change echo response validation so a stored bind UUID for the target domain is accepted as a valid `To`
- [x] Add regression coverage for bind-backed echo replies and keep invalid `To` failures intact
- [x] Refresh docs and lessons to match the accepted echo behavior
- [x] Run targeted verification and capture the review

# Review

- Updated `python/pollyweb_cli/features/echo.py` so `pw echo` accepts a response `To` that matches either the normalized target domain or that domain's stored bind UUID from `binds.yaml`.
- Threaded `BINDS_PATH` into the echo command entrypoint in `python/pollyweb_cli/cli.py` so echo verification can reuse the same canonical bind lookup rules as wallet-backed sending.
- Added regression coverage in `tests/test_echo.py` for a bind-backed echo reply and for an unrelated UUID still failing the `To` check.
- Extended `tests/cli_test_helpers.py` so tests can build signed raw JSON echo payloads for UUID `To` values, matching the server behavior that bypasses local `Msg` domain validation.
- Updated `docs/commands/echo.md`, `README.md`, and `tasks/lessons.md` to document the accepted bind-backed echo behavior.
- Verified with `./.venv/bin/python -m pytest -q tests/test_echo.py` and `git diff --check`.
