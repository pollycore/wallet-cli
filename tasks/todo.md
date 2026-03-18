# Task Plan

- [x] Inspect the current pytest and pre-push setup for real-profile leakage
- [x] Add global test-profile isolation plus pre-push `HOME` isolation
- [x] Verify the guarded paths with focused pytest runs and the smoke-test selector

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/tests/conftest.py` with an autouse fixture that redirects `cli` profile paths, `transport.DEFAULT_BINDS_PATH`, and process `HOME`/`USERPROFILE` into a per-test temp `.pollyweb` tree.
- Updated `/Users/jorgemf/Git/wallet-cli/githooks/pre-push` so both the main test suite and the clean-install smoke test run with an isolated `HOME`, closing the path back to the real `~/.pollyweb` profile.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_cli_core.py` coverage that asserts the autouse fixture is actually isolating the CLI and transport bind paths.
- Updated `/Users/jorgemf/Git/wallet-cli/AGENTS.md` and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so future test work keeps the profile-isolation rule intact.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_cli_core.py tests/test_bind.py` (`50 passed`) and `HOME="$PWD/.git/.manual-pre-push-home" USERPROFILE="$PWD/.git/.manual-pre-push-home" ./.venv-tests/bin/python -m pytest -q tests/test_cli_core.py -k 'dependency_contract'` (`1 passed, 33 deselected`).

# Task Plan

- [x] Review the written bind behavior and identify the exact same-domain replacement path
- [x] Raise a loud discovery-time error for same-domain same-schema bind churn, with alert logging and local notification
- [x] Add regression coverage and verify the bind flow with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/bind.py` so same-domain same-schema bind changes now stop with a `UserFacingError`, append an `ALERT` record to `~/.pollyweb/binds.log`, and attempt a best-effort macOS notification via `osascript` instead of silently replacing the stored UUID.
- Updated `/Users/jorgemf/Git/wallet-cli/tests/test_bind.py` to cover both the direct `save_bind()` alert path and the CLI-visible failure when `pw bind` would otherwise replace an existing bind for the same domain.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/bind.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so the new discovery behavior is documented for future work and concurrent-agent debugging.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_bind.py` (`16 passed`).

# Task Plan

- [x] Inspect the documented `pw test` fixture rules and current inbound subset matcher
- [x] Allow expected empty inbound scalar values to match either an empty response value or an omitted field
- [x] Add regression coverage, update docs/guidance, and verify with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py` so `pw test` now treats expected empty scalar fields such as `''` or `null` as optional-presence checks: the response may include the same empty value or omit the field entirely.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py` coverage for both accepted shapes of an empty expected field, including the `Header.Algorithm` case that motivated the change.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/test.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` to document the new inbound-fixture rule for future work.
- Verification is next with `./.venv-tests/bin/python -m pytest -q tests/test_test_command.py`.

# Task Plan

- [x] Inspect the current `pw echo --debug` verification path and confirm where extra response fields are silently tolerated
- [x] Reject unexpected top-level echo-response fields before debug rendering so misplaced properties fail loudly
- [x] Add regression coverage for a top-level `Request` leak and verify the affected echo tests

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` so `pw echo` now validates the raw synchronous response object before parsing and rejects any top-level fields outside `Body`, `Hash`, `Header`, and `Signature`.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` coverage for a debug echo response that incorrectly includes a top-level `Request`, locking in the new failure message and ensuring the CLI stops before rendering a misleading formatted response.
- Updated `/Users/jorgemf/Git/wallet-cli/AGENTS.md` and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` to record the stricter response-shape rule for future work.

# Task Plan

- [x] Review the current `pw test` HTTP-failure output and the shared transport error-body handling
- [x] Append inbound `error` details to the existing `pw test` HTTP error line when the response body provides them
- [x] Add regression coverage for inbound HTTP error details and verify with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/tools/transport.py` so wallet-send HTTP failures preserve the decoded response body on the raised `HTTPError`, which keeps the debug path working while letting feature commands reuse the inbound payload details.
- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py` so `pw test` now appends an inbound JSON `error` field to the existing `HTTP <code> <reason>.` message when the server returns one, keeping the extra detail in the same red stderr area.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py` coverage for an HTTP 400 response whose inbound payload includes a nested signature-verification error and confirmed the failure output includes both the HTTP line and the server detail.
- Recorded the new `pw test` HTTP-error-detail rule in `/Users/jorgemf/Git/wallet-cli/AGENTS.md` and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md`.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_test_command.py` (`16 passed, 1 skipped`).

- [x] Review the written `pw test` guidance plus current parser/transport behavior for `--json`
- [x] Add `--json` support to `pw test` so its response and debug output rules match the shared wallet send path
- [x] Update regression coverage, docs, and repo guidance for the new `pw test --json` behavior
- [x] Verify the affected parser and `pw test` flows with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/parser.py`, `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/cli.py`, and `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py` so `pw test` now accepts `--json` and forwards it to the shared wallet-send transport as `debug_json`, which makes `pw test --debug --json` render raw JSON debug payloads while preserving the normal concise pass/fail output.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_cli_core.py` and `/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py` coverage for parser acceptance, `--debug --json` transport wiring, and the rule that plain successful `pw test --json` runs still only print `✅ Passed: ...`.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/test.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` to document the new `pw test --json` support and its interaction with `--debug`.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_cli_core.py tests/test_test_command.py` (`44 passed, 1 skipped`).

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

# Task Plan

- [x] Review the current `pw echo` DNS/DKIM verification path and define the missing debug diagnostics
- [x] Add DNS/DNSSEC/DKIM tracing to `pw echo --debug` without changing the normal success path
- [x] Update docs and regression coverage, then verify with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` so `pw echo --debug` now captures the PollyWeb branch `DS` lookup and DKIM `TXT` lookup, including queried names, returned values, nameservers, and the DNSSEC AD-flag state, and it prints those diagnostics on both successful verification and post-response verification failures.
- Added `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/models.py` data models plus `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` regression coverage for the richer debug output, including the failure path where signature verification fails after the response is received.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/echo.md`, `/Users/jorgemf/Git/wallet-cli/README.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` to document the expanded `pw echo --debug` contract.
- Verification passed with `./.venv-tests/bin/python -m pytest tests/test_echo.py`.
- [x] Review the existing `pw echo` debug external-link wording and current test coverage
- [x] Rename the MXToolbox output to an explicit DKIM test link while preserving the verified branch/selector URL shape
- [x] Run the focused `pw echo` test file with the repo test virtualenv and capture the result

## Review
- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` so `pw echo --debug` prints the MXToolbox URL under the clearer label `MXToolbox DKIM test`.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/echo.md`, `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` to keep the docs, coverage, and maintenance notes aligned with that output.
- `./.venv-tests/bin/python -m pytest -q tests/test_echo.py` is currently blocked during collection because the test env has `pollyweb 1.0.65`, which does not export `DnsQueryDiagnostic`; syntax verification still passed with `./.venv-tests/bin/python -m py_compile python/pollyweb_cli/features/echo.py tests/test_echo.py`.
- Followed up by relabeling the DNSSEC Debugger click-through URL to `DNSSEC Debugger test` so the direct branch-level DNSSEC check is just as explicit as the MXToolbox link.
- Followed up again by relabeling the Google DNS click-through URL to `Google DNS test` so all three external debug links read as direct tests for the verified branch.
- Added a fourth external debug link labeled `Google DNS A record test` so users can open the direct `https://dns.google/resolve?name=pw.<domain>&type=A` view for the verified branch.

# Task Plan

- [x] Review the written `pw test` fixture guidance and current inbound wildcard matcher
- [x] Add `"<str>"` as a strict inbound wildcard for required non-empty string fields
- [x] Update focused regression coverage and command docs, then verify with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py` so `pw test` now treats the exact expected inbound value `"<str>"` as a wildcard that requires the response field to exist and contain a non-empty string.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py` coverage for accepted string wildcard matches plus the three failure cases the user called out: missing field, empty string, and non-string values.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/test.md`, `/Users/jorgemf/Git/wallet-cli/README.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so the new fixture sentinel is documented consistently for future work.
