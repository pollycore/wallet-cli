# Task Plan

- [x] Review the written `pw msg` debug/output guidance and inspect the shared debug formatter path
- [x] Accept `--json` alongside `--debug` so debug payloads render as raw JSON when both flags are present
- [x] Update regression coverage and docs for the combined debug/json behavior
- [x] Verify the affected parser, formatter, and `pw msg` flows with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/tools/debug.py`, `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/tools/transport.py`, and `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/msg.py` so `pw msg --debug --json` now prints outbound and inbound debug payloads as raw JSON while keeping plain `--debug` YAML-style output and plain `--json` raw final-response output unchanged.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_msg_command.py` coverage for the combined `--debug --json` path and confirmed the existing parser coverage still accepts both flags together.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/msg.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` to record the combined-flag behavior and the shared debug-formatting rule.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_msg_command.py tests/test_cli_core.py` (`45 passed`).

# Review

- Replaced the abandoned OS-level watcher approach with a wallet-owned audit path in `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/bind.py`, so `pw bind` now appends bind-change entries to `~/.pollyweb/binds.log` whenever it persists `~/.pollyweb/binds.yaml`.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_bind.py` coverage for both first-time bind creation and replacement of an existing bind entry, including the expected log contents and file permissions.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/bind.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so the new bind-audit behavior is documented alongside the existing bind persistence rules.

# Task Plan

- [x] Review the written bind-response contract and confirm the parser mismatch against the reported JSON response
- [x] Accept JSON bind replies that return either `Bind:<UUID>` or a bare UUID while preserving current storage behavior
- [x] Add regression coverage for the bare-UUID JSON bind response and verify the bind test suite
- [x] Capture the review and record the lesson in repo guidance

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/bind.py` so `pw bind` now treats a bare UUID as the primary successful bind response shape, keeps legacy `Bind:<UUID>` compatibility, and reports the accepted formats accurately in bind-token errors.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_bind.py` coverage for a JSON bind response whose `Bind` value is a bare UUID and verified that the stored bind stays UUID-only.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/bind.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so the repo guidance now documents bare UUID responses as the expected shape while preserving prefixed compatibility.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_bind.py` (`13 passed`).

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

# Task Plan

- [x] Review the written instructions and current `pw test` success output behavior
- [x] Keep passing `pw test` output concise: dynamic runs show only `✅ Test passed`, file-backed runs include the fixture path and do not print the received message
- [x] Update regression coverage and docs for the new success output
- [x] Run targeted verification and capture the review

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py` so successful `pw test` runs no longer print the received message and now format success output based on whether the user supplied fixture paths.
- Tightened `/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py` to lock in `✅ Passed: <filename-without-extension>` for explicit fixture runs and default `pw-tests` sweeps alike.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/test.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` to document the concise success-output rule.
- Verified with `./.venv/bin/python -m pytest -q tests/test_test_command.py` (`12 passed, 1 skipped`).

# Task Plan

- [x] Review the written upgrade instructions and inspect the automatic self-update implementation
- [x] Suppress noisy pip output during automatic upgrades and replace it with a transient spinner plus concise completion notice
- [x] Add regression coverage for quiet subprocess execution and the upgrade status messaging
- [x] Run targeted verification and capture the review

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/cli.py` so automatic preflight upgrades run `pip` quietly, show a transient spinner with the requested version text, and leave a short completion notice before re-execing the original command.
- Expanded `/Users/jorgemf/Git/wallet-cli/tests/test_cli_core.py` to lock in quiet subprocess execution, spinner configuration, and the final upgrade notice while keeping the existing re-exec and failure-path coverage intact.
- Recorded the new upgrade-output expectation in `/Users/jorgemf/Git/wallet-cli/AGENTS.md` and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md`.
- Refreshed the editable install with `./.venv/bin/python -m pip install -e '.[dev]'`, then verified with `./.venv/bin/python -m pytest -q tests/test_cli_core.py` (`27 passed`) and `./.venv/bin/python -m pytest -q tests/test_echo.py` (`8 passed`).

# Task Plan

- [x] Review the written `pw echo` guidance and current DNS-failure handling
- [x] Convert unresolved echo target domains into a human-readable inbox-host error
- [x] Add regression coverage for the `any-non-existing.dom` resolver failure path
- [x] Run targeted verification and capture the review

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` so `pw echo` now translates resolver failures into the same human-readable PollyWeb inbox-host guidance already used by bind flows.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` coverage that simulates `pw echo any-non-existing.dom` failing with `socket.gaierror(...)` and locks in the user-facing message.
- Recorded the new expectation in `/Users/jorgemf/Git/wallet-cli/AGENTS.md` and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md`.
- Verification is running with the repo test interpreter and a direct CLI repro for `pw echo any-non-existing.dom`.

# Task Plan

- [x] Inspect the pre-push failures in `pw` error rendering and `pw test` DNS handling
- [x] Restore the expected user-facing error prefixes without broad CLI behavior changes
- [ ] Run the targeted test coverage and retry the guarded push

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/cli.py` so the top-level `UserFacingError` renderer prints `Error: ...` again, matching the documented CLI contract and the existing regression coverage.
- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py` so DNS failures in `pw test` continue to surface the human-readable inbox-host guidance while preserving the expected `HTTP 502 Bad Gateway.` prefix.
- Verification is next: targeted pytest for the three failing cases, then the guarded `git push` retry.

# Task Plan

- [x] Review the written `pw msg` output guidance and inspect the current response rendering path
- [x] Change `pw msg` to print YAML-formatted responses by default while adding `--json` for raw output
- [ ] Update docs and regression coverage, then verify the affected command paths

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/msg.py` so `pw msg` now renders its synchronous response with the shared YAML formatter by default and only prints the raw response when `--json` is set.
- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/parser.py`, `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/cli.py`, and `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/tools/debug.py` to expose the new flag and reuse the existing debug YAML rendering logic without duplicating formatting code.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/msg.md` and the `pw msg` regression tests to reflect the new default YAML output and the `--json` override.

# Task Plan

- [x] Review the upgrade guidance and current installer path for likely failure modes
- [x] Add retry and non-venv fallback behavior to make automatic upgrades more robust
- [ ] Add regression coverage and verify the hardened self-upgrade flow

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/cli.py` so automatic upgrades retry the pip install once before failing and fall back to `--user` when the CLI is running outside a virtualenv.
- Expanded `/Users/jorgemf/Git/wallet-cli/tests/test_cli_core.py` to lock in the new pip command shape, retry behavior, and the `--user` fallback path.
- Recorded the new self-upgrade reliability rule in `/Users/jorgemf/Git/wallet-cli/AGENTS.md` and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md`.
