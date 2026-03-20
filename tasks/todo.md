- [x] Inspect the `pw test` fixture path resolution flow
- [x] Add coverage for `pw test <name>` resolving `./pw-tests/<name>` directories
- [x] Update `pw test` path resolution to treat bare names as `./pw-tests/<name>` when that fallback is a directory
- [x] Run focused pytest verification
- [x] Capture the new path-resolution lesson in `tasks/lessons.md`

## Review

- Added the `./pw-tests/<name>` directory fallback for bare `pw test <name>` arguments while keeping literal existing paths higher priority.
- Added focused coverage for the named-subdirectory shortcut and the precedence rule when a same-named explicit file exists.
- Verified with `./.venv-tests/bin/python -m pytest tests/test_test_command.py`.
