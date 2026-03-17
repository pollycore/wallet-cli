# Task Plan

- [x] Review the written instructions, docs, and current upgrade-preflight behavior
- [x] Change the upgrade prompt so plain `Enter` declines instead of upgrading
- [x] Add regression tests for explicit yes, explicit no, and empty-input prompt behavior
- [x] Refresh the user-facing docs to match the safer default
- [x] Run targeted verification and capture the lesson

# Review

- Changed the self-upgrade prompt in `python/pollyweb_cli/cli.py` from `[Y/n]` to `[y/N]` and made empty input decline instead of upgrade.
- Added focused regression tests in `tests/test_cli_core.py` for empty input, explicit `y`, and explicit `n`.
- Updated `README.md` to state that only `y` or `yes` upgrades, and that pressing `Enter` declines.
- Recorded the prompt-default lesson in `tasks/lessons.md`.
- Verified with `./.venv/bin/python -m pytest -q tests/test_cli_core.py -k 'prompt_for_upgrade or preflight or version_flag'`.
