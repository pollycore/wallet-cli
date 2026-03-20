# Task Plan

- [x] Inspect the parallel `pw test` renderer and completion flow to find where rows were being cleared before their final status rendered
- [x] Change the renderer handoff so resolved pass/fail rows stay visible long enough to replace the spinner in place
- [x] Add focused regression coverage and verify with the repo test interpreter

# Review

- Updated [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py) so parallel fixture rows use an explicit status scope and a renderer-side rendered-event handshake, which lets `✅ Passed` or `❌ Failed` replace the spinner row before that row is retired.
- Kept the existing hierarchical parallel view and group summaries intact while removing the pop-before-resolve gap that caused completed rows to vanish until later output.
- Added focused renderer regression coverage in [/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py](/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py) for both success and failure replacement while a sibling row is still active.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_test_command.py -k 'parallel_group_prints_completed_success_before_group_finishes or parallel_group_prints_completed_failure_before_group_finishes or parallel_folder_group_prints_nested_success_before_sibling_folder_finishes or without_debug_runs_same_folder_numeric_prefix_group_in_parallel or parallel_status_renderer_waits_for_last_status_close'`.
