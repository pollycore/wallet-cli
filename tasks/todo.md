# Task Plan

- [x] Inspect the documented and implemented `pw test` HTTP-failure behavior
- [x] Allow expected non-200 HTTP responses to validate through `Inbound.Meta.Code`
- [x] Add focused regression coverage for expected and unexpected HTTP error codes
- [x] Update docs and lessons, then verify in the repo test environment

# Review

- Updated [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py) so `pw test` no longer fails immediately on every `urllib.error.HTTPError`: when a fixture explicitly expects the same status in `Inbound.Meta.Code` and the HTTP error carries a response body, the command now validates that body through the normal inbound subset matcher and can pass expected non-200 cases such as `404`.
- Added focused regression coverage in [/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py](/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py) for the new pass path and for the unchanged mismatch failure path.
- Updated [/Users/jorgemf/Git/wallet-cli/docs/commands/test.md](/Users/jorgemf/Git/wallet-cli/docs/commands/test.md) and [/Users/jorgemf/Git/wallet-cli/tasks/lessons.md](/Users/jorgemf/Git/wallet-cli/tasks/lessons.md) to document the expected-HTTP-error fixture rule.
- Verified with `./.venv-tests/bin/python -m pytest tests/test_test_command.py -k "matches_expected_inbound_meta_code or reports_http_failures_with_fixture_path or reports_inbound_error_details_for_http_failures or fails_when_response_meta_reports_server_error"`.
