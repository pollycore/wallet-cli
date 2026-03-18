# Task Plan

- [x] Review the written instructions and current `pw echo` success output behavior
- [x] Keep non-debug `pw echo` success output to the verification line only
- [x] Update regression coverage to prevent the response payload from printing on success
- [x] Capture the output preference in repo guidance
- [x] Run targeted verification and capture the review

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` so plain `pw echo` no longer prints the echoed payload on success and now reserves payload rendering for `--debug`.
- Tightened `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` so the default success path must print only `Verified echo response: ✅`.
- Updated `/Users/jorgemf/Git/wallet-cli/AGENTS.md` and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` to record that quiet success output is the intended default for `pw echo`.
- Refreshed the local editable install with `./.venv/bin/python -m pip install -e '.[dev]'`, then verified with `./.venv/bin/python -m pytest -q tests/test_echo.py` (`8 passed`).
