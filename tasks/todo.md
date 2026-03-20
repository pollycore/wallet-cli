# Task Plan

- [x] Inspect the parallel `pw test` result rendering path and current renderer behavior
- [x] Keep parallel failure details from surfacing above the settled result list
- [x] Render failed parallel fixture rows in red in the live/final status output
- [x] Add targeted regression coverage and verify with the repo test environment

# Review

- Updated [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py) so parallel `pw test` failures that already rendered a `❌ Failed:` row no longer bubble a generic CLI stderr error ahead of the settled list; the command now prints the detailed failure message after the parallel renderer closes, and failed live rows render red on interactive terminals.
- Added focused regression coverage in [/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py](/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py) for red failed-row styling and for the command-level deferred parallel failure detail output.
- Verified with `./.venv-tests/bin/python -m pytest tests/test_test_command.py -k "renders_failed_rows_in_red or cmd_test_prints_parallel_failure_detail_after_settled_output or parallel_folder_failure_reports_nested_fixture_path"` and `./.venv-tests/bin/python -m pytest tests/test_test_command.py -k "test_test_parallel_folder_failure_reports_nested_fixture_path or test_test_reports_http_failures_with_fixture_path or test_cmd_test_prints_parallel_failure_detail_after_settled_output"`.
