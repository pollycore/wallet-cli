# Tests Index

This folder is organized by CLI feature so future changes can stay local:

- `test_cli_core.py`: parser, version, `pw upgrade`, automatic upgrade preflight, and generic CLI rendering helpers
- `test_chat.py`: AppSync chat helpers and `pw chat`
- `test_config.py`: `pw config` and config persistence behavior
- `test_bind.py`: `pw bind`, bind storage, and bind-network error handling
- `test_msg_command.py`: `pw msg` input parsing and wallet-backed sending
- `test_test_command.py`: `pw test`
- `test_echo.py`: `pw echo` transport and response verification
- `test_sync.py`: `pw sync` and sync file map generation
- `test_onboard.py`: notifier onboarding helpers used by `pw config`
- `cli_test_helpers.py`: shared constants, fake transport objects, and setup helpers
- `conftest.py`: repo-wide pytest setup and the autouse upgrade-check skip fixture

## LLM Notes

- Add new tests to the narrowest existing feature file instead of growing a catch-all module.
- If multiple files need the same fake object or setup routine, move that helper into `cli_test_helpers.py` rather than copying it.
- Keep behavior-specific assertions close to the command they cover. Avoid centralizing unrelated assertions in a shared file.
- When splitting or renaming tests, run the full suite to catch fixture-discovery and import issues, especially around `conftest.py`.
- Prefer names shaped like `test_<command>_<behavior>` so failures stay easy to scan.
