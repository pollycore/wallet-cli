- [x] Inspect the `pw test` fixture path resolution flow
- [x] Add coverage for explicit directory arguments to `pw test`
- [x] Update `pw test` to run every YAML fixture inside an explicit directory path
- [x] Run focused pytest verification
- [x] Capture the folder-discovery lesson in `tasks/lessons.md`

## Review

- Implemented explicit directory support for `pw test` by reusing the same recursive sorted `*.yaml` discovery pattern as the default `./pw-tests` sweep.
- Added focused tests for explicit directory recursion and the empty-directory user-facing error.
- Verified with `./.venv-tests/bin/python -m pytest tests/test_test_command.py`.
