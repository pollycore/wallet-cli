# Task Plan

- [x] Inspect the current `pw echo` feature boundaries and define smaller sub-feature modules that preserve the existing `echo.py` facade
- [x] Move `pw echo` parsing, metadata, rendering, and Textual viewer internals into sibling modules while keeping test-facing exports stable
- [x] Verify the refactor with focused echo tests in the repo virtualenv and record any new maintenance lesson

# Review

- Split `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` and `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo_presentation.py` into smaller sibling sub-feature modules for models, response parsing, runtime orchestration, rendering, section building, and the Textual viewer.
- Kept `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` as the command and compatibility facade, and kept `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo_presentation.py` as the presentation facade so existing tests and nearby imports can keep using the old module paths.
- Restored the old patchable surface on `pollyweb_cli.features.echo`, including helpers such as `send_wallet_message`, `DEBUG_CONSOLE`, payload renderers, section builders, and the legacy `_resolve_echo_command(..., transport_debug=...)` call shape.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_echo.py` (`39 passed`).

- [x] Review the current `pw echo --debug` startup flow and isolate the network-bound work from the Textual render path
- [x] Keep the request phase in the terminal with a `Sending message...` spinner, then open the Textual viewer only after the success or failure sections are fully prepared
- [x] Add focused regression coverage for the new spinner-first flow and verify with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` so interactive `pw echo --debug` now resolves the request and prebuilds the final Textual sections behind a terminal `Sending message...` spinner, then opens the viewer only after the final success or failure content is ready.
- Updated `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` with a regression that locks in the spinner lifecycle and confirms the Textual app opens only after the request phase completes.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/echo.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so the new spinner-first interactive debug behavior is documented for future work.
- Verified with `./.venv-tests/bin/python -m py_compile python/pollyweb_cli/features/echo.py python/pollyweb_cli/features/echo_presentation.py` and `./.venv-tests/bin/python -m pytest -q tests/test_echo.py` (`38 passed`).

- [x] Inspect the current `pw test` timing calculation and the wrapped sync response metadata shape
- [x] Update `pw test` to consider `Response.Meta.TotalMs` when formatting total duration and latency share
- [x] Add focused regression coverage for metadata-backed `pw test` timing and verify with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py` so `pw test` now inspects wrapped synchronous responses for `Response.Meta.TotalMs` and uses that value as a timing hint for the displayed total duration and latency share, while preserving a larger local wall-clock measurement when present.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py` coverage for the helper that reads wrapped timing metadata and for the command-level success line that now reflects `Response.Meta.TotalMs`.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/test.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so the metadata-backed `pw test` timing rule is documented for future work.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_test_command.py` (`37 passed, 1 skipped`).

# Task Plan

- [x] Inspect the interactive `pw echo --debug` Textual viewer and confirm where keyboard bindings reach the scrollable body
- [x] Add arrow-key and page-scroll actions that forward into the existing `VerticalScroll` body without changing the Rich render path
- [x] Verify with focused echo tests and document the new viewer navigation shortcut

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo_presentation.py` so the interactive `pw echo --debug` Textual viewer now binds `Up`, `Down`, `Page Up`, and `Page Down` to explicit app actions that forward scrolling into the existing `#body` `VerticalScroll` widget with animation disabled.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` coverage that locks in both the new scroll bindings and the forwarding behavior to the scrollable body without needing a live Textual DOM.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/echo.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so the interactive viewer navigation contract is documented for future work.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_echo.py` (`37 passed`).

- [x] Review the written `pw echo` timing contract and the current sync-wrapper metadata paths
- [x] Extend `pw echo` network timing to learn from wrapped sync `Meta` / `Response.Meta` and show explicit client overhead in milliseconds
- [x] Verify with focused echo coverage in the repo test interpreter and capture any reusable lesson

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` so `pw echo` now merges timing hints from direct reply body metadata plus wrapped sync `Meta` and `Response.Meta` before rendering the debug timing section.
- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo_presentation.py` so `Network timing` now always prints an explicit `Client overhead` line and also renders wrapped-response timing fields such as `Remote latency`, `Total execution`, and `Downstream execution` when present.
- Updated `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` and `/Users/jorgemf/Git/wallet-cli/docs/commands/echo.md` to lock in the richer timing output and document the expanded metadata sources.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_echo.py` (`34 passed`).

# Task Plan

- [x] Profile `pw echo --debug` startup and identify the main UI/rendering bottlenecks
- [x] Make the interactive echo viewer build heavy payload sections lazily and reuse parsed payload data
- [x] Add focused regression coverage for the lazy section path and verify with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` and `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo_presentation.py` so the interactive `pw echo --debug` viewer now opens on the pretty JSON payload view by default, builds each payload-format section list lazily on first use instead of precomputing YAML/JSON/raw before launch, and reuses parsed inbound payload data across those views.
- Tightened `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo_presentation.py` so payload-style sections serialize their payload only once and reuse that same text for both the renderable body and the section clipboard copy action.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` coverage for the lazy per-view section caching and for the command-level default interactive payload format.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/echo.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so future echo work preserves the faster interactive startup path.
- Verified with `./.venv-tests/bin/python -m pip install -e '.[dev]'` and `./.venv-tests/bin/python -m pytest -q tests/test_echo.py` (`35 passed`), then spot-measured the render cost on a large sample payload: YAML about `541 ms`, pretty JSON about `3 ms`, raw JSON about `3 ms`.

- [x] Trace the current wrapped echo-response failure and confirm whether the parser rejects the outer sync envelope before unwrapping `Response`
- [x] Move wrapped synchronous response validation into `pollyweb` so the library owns the `Request`/`Response`/`Meta` rule and unwraps the nested reply
- [x] Update `wallet-cli` echo parsing to use the shared library sync-response path, add regression coverage, and verify both repos with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/pollyweb-pypi/pollyweb/msg.py` so `Msg.parse(..., sync_response = True)` now validates the outer synchronous `Request`/`Response`/`Meta` envelope and unwraps the nested `Response` message before normal PollyWeb parsing and verification.
- Added `/Users/jorgemf/Git/pollyweb-pypi/tests/test_msg.py` coverage for both the accepted wrapped-response path and the new rejection wording when callers still send `Metadata` instead of `Meta`, and documented the API in `/Users/jorgemf/Git/pollyweb-pypi/docs/msg.md`, `/Users/jorgemf/Git/pollyweb-pypi/docs/msg/parse.md`, and `/Users/jorgemf/Git/pollyweb-pypi/RELEASES.md`.
- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` to rely on `pollyweb.Msg.parse(..., sync_response = True)` instead of a CLI-owned top-level allow-list, and refreshed `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` plus the local docs/guidance to match the new wrapper contract.

# Task Plan

- [x] Inspect the current `pw echo` response-header extraction and confirm where remote DKIM selector assessment comes from today
- [x] Update `pw echo` to prefer `msg.Response.Header.Selector` when assessing remote DKIM context from wrapped sync responses
- [x] Add focused regression coverage for wrapped-response selector assessment and verify with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` so debug failure reply details now assess the signed selector and signature/hash presence from the nested `Response` message when a synchronous payload is transport-wrapped.
- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo_presentation.py` so external DKIM/DNS reference links prefer `Response.Header.Selector` and `Response.Header.From` over wrapper headers.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` coverage for wrapped echo responses to lock the CLI to the nested remote selector.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/echo.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` to document the wrapped-response DKIM assessment rule.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_echo.py`.

- [x] Trace the interactive echo viewer quit behavior and confirm why `Ctrl+C` does not close the app
- [x] Bind `Ctrl+C` and other common terminal close keys directly to the viewer quit action
- [x] Add focused regression coverage and verify with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo_presentation.py` so the interactive `pw echo --debug` viewer now treats `Ctrl+C`, `Ctrl+W`, `q`, `x`, and `Esc` as direct quit keys instead of falling back to Textual's inherited quit-help toast.
- Updated `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` to lock in both the common quit bindings and the underlying quit action behavior on the viewer app.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_echo.py`.

# Task Plan

- [x] Inspect the `pw echo --debug` failure renderer and confirm why the DNS and signature-related sections disappear behind the error summary
- [x] Keep a reply-details section and DNS diagnostics section visible for debug failures, including parse/shape failures with no library DNS diagnostics
- [x] Verify with focused echo tests, then record the maintenance note

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` to derive best-effort reply details from any received echo response before rendering debug failures, so signature-related fields still appear alongside the error summary.
- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo_presentation.py` so debug failure output always renders both a reply-details block and a `DNS verification diagnostics` block; when library diagnostics are unavailable, the section now says so instead of disappearing.
- Updated `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` to lock in both regression cases: unexpected top-level fields and signature-verification failures must still show the reply-details and DNS sections.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_echo.py` (`28 passed`).

- [x] Inspect the `pw echo` failure render path and confirm why the inbound payload disappears on validation errors
- [x] Pass the raw inbound response through the debug failure renderer so both console and Textual views still show it
- [x] Verify with focused echo tests and record the maintenance note

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` and `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo_presentation.py` so `pw echo --debug` now carries any received synchronous response into the failure renderer, which keeps the inbound payload visible in both the plain debug output and the interactive Textual viewer even when later parse or verification checks fail.
- Updated `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` to lock in the regression case where an echo reply contains unexpected top-level fields: the command must still show the inbound payload before the error summary.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/echo.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so the debug failure contract is documented for future work.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_echo.py` (`27 passed`).

- [x] Split `pw echo` presentation helpers into a dedicated module while keeping command logic in `echo.py`
- [x] Preserve the existing test-facing helper surface and update imports without changing behavior
- [x] Verify the affected echo/debug suites with the repo test interpreter

- [ ] Add copy metadata to interactive echo payload sections so each block can expose its own clipboard action
- [ ] Render per-section copy buttons next to payload block titles in the Textual echo viewer
- [ ] Add focused regression coverage and verify with the repo test interpreter

- [x] Trace the interactive `pw echo --debug --json` render path and confirm why JSON colors disappear after Textual mounts
- [x] Reuse syntax-colored JSON renderables inside the Textual echo viewer so the final app render keeps colors
- [x] Add focused regression coverage and verify with the repo test interpreter
- [x] Add hierarchical indentation to the interactive JSON renderables without changing script-safe compact JSON output

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/tools/debug.py` so the shared Rich JSON syntax renderable now uses indented multi-line JSON for human-facing displays, while the non-interactive `print_json_payload()` path still emits compact JSON for scripts.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_debug_tools.py` and `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` coverage that locks the interactive JSON renderables to syntax-highlighted, pretty-indented output without changing the captured non-TTY `--json` behavior.
- Recorded the interactive JSON indentation rule in `/Users/jorgemf/Git/wallet-cli/AGENTS.md` and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md`.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_debug_tools.py tests/test_echo.py` (`26 passed`).

- [x] Trace the interactive `pw echo --debug --json` render path and confirm why JSON colors disappear after Textual mounts
- [x] Reuse syntax-colored JSON renderables inside the Textual echo viewer so the final app render keeps colors
- [x] Add focused regression coverage and verify with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/tools/debug.py` to expose shared compact-JSON and Rich JSON-syntax builders, then updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` so the interactive Textual echo viewer reuses that syntax-colored JSON renderable instead of repainting payload sections as plain white text.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` coverage to lock the Textual JSON payload renderable to `rich.syntax.Syntax`, while keeping `/Users/jorgemf/Git/wallet-cli/tests/test_debug_tools.py` coverage on the shared terminal/non-terminal JSON helper behavior.
- Recorded the Textual repaint gotcha in `/Users/jorgemf/Git/wallet-cli/AGENTS.md` and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md`.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_debug_tools.py tests/test_echo.py` (`24 passed`).

- [x] Review the shared `--json` output contract and current debug formatter path
- [x] Add terminal-aware colorized JSON rendering without breaking script-friendly raw JSON output
- [x] Add focused regression coverage and verify with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/tools/debug.py` so shared `--json` output now uses Rich JSON syntax coloring on interactive terminals while preserving the same compact raw JSON text on non-interactive/scripted output.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_debug_tools.py` coverage for both the interactive colorized path and the non-interactive plain-JSON path.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/echo.md`, `/Users/jorgemf/Git/wallet-cli/docs/commands/msg.md`, `/Users/jorgemf/Git/wallet-cli/docs/commands/test.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so the terminal-aware JSON-coloring contract is documented for future work.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_debug_tools.py tests/test_echo.py tests/test_msg_command.py tests/test_test_command.py` (`70 passed, 1 skipped`).

- [x] Inspect the interactive `pw echo --debug` Textual body path and confirm why styles are stripped
- [x] Restore Rich/Textual body rendering so the interactive echo viewer keeps colors
- [x] Add focused regression coverage and verify with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` so the interactive `pw echo --debug` Textual viewer renders its body sections through Rich `Static(Group(...))` widgets again instead of flattening them into a plain `TextArea`, which restores the intended debug colors.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` coverage for the Textual compose path so future viewer refactors keep Rich section renderables in the interactive body.
- Kept `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` compatible with PollyWeb `Struct` response metadata so `Network timing` still shows `TotalExecutionMs` and `DownstreamExecutionMs`.
- Recorded the viewer-color lesson in `/Users/jorgemf/Git/wallet-cli/AGENTS.md` and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md`.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_echo.py` (`21 passed`).

- [x] Review the current `pw echo --debug` timing section and confirm where reply `Body.Metadata` can be read safely
- [x] Add echo metadata performance metrics plus latency milliseconds to the shared `Network timing` render path
- [x] Update docs/guidance, add regression coverage, and verify with the repo test interpreter

- [x] Reproduce the `pw-dev echo --debug` `!!python/object` leak and trace the shared debug formatting path
- [x] Fix the echo Textual/YAML rendering so wrapped debug strings use the same literal-block serializer as the shared formatter
- [x] Add regression coverage and verify with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` so the shared `Network timing` section now prints `Body.Metadata.TotalExecutionMs` and `Body.Metadata.DownstreamExecutionMs` when present on a verified echo reply, and `Latency share` now includes both the percentage and the network total in milliseconds.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` coverage for the new metadata-backed timing lines so both the render shape and the latency-millisecond format stay locked in.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/echo.md` and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so the new echo timing contract is documented for future work.

- [x] Review the current `pw echo` output contract and align a format switch with the existing `msg`/`test` behavior
- [x] Add `pw echo` YAML/JSON output switching without changing the default concise verification flow
- [x] Update echo docs/guidance, add regression coverage, and verify with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/parser.py`, `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/cli.py`, and `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` so `pw echo` now accepts `--json`, prints the raw synchronous response on non-debug success, and switches debug payload-style sections to raw JSON when combined with `--debug`.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` and `/Users/jorgemf/Git/wallet-cli/tests/test_cli_core.py` coverage for the new parser flag and both `pw echo --json` output modes while preserving the existing concise default behavior.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/echo.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so the new echo formatting contract is documented for future work.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_echo.py tests/test_cli_core.py` (`58 passed`).

- [x] Install `textual` and wire `pw echo` to use a reactive TTY-only viewer without breaking script output
- [x] Keep non-interactive `pw echo` behavior stable, update docs/guidance, and verify with the repo test interpreter

- [x] Inspect the current wallet-backed `pw msg` transport path and compare it with the written "use pollyweb" guidance
- [x] Switch wallet-backed request construction to the published `pollyweb.Msg.from_outbound(...)` API
- [x] Add regression coverage for the shared transport build path and verify with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/tools/transport.py` so wallet-backed sends now build outbound requests through the published `pollyweb.Msg.from_outbound(...)` API while keeping wallet sender selection and debug rendering unchanged.
- Updated `/Users/jorgemf/Git/wallet-cli/pyproject.toml` to require the published `pollyweb>=1.0.79` release that adds `Msg.from_outbound(...)`.
- Updated `/Users/jorgemf/Git/wallet-cli/tests/test_msg_command.py` and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so the shared transport path is locked to the library builder and future CLI changes do not reintroduce a local message wrapper.
- Verified with `./.venv-tests/bin/python -m pip install --upgrade pollyweb==1.0.79` and `./.venv-tests/bin/python -m pytest -q tests/test_msg_command.py tests/test_test_command.py` (`47 passed, 1 skipped`).

- [x] Review the written `pw echo` output contract and current render path for a new top header
- [x] Add a boxed top header to `pw echo` without disturbing the existing verification/debug sections
- [x] Update echo docs/guidance, add regression coverage, and verify with the repo test interpreter

- [x] Trace the raw `pw-dev echo` resolver traceback to the shared wallet transport path
- [x] Normalize low-level wallet transport connection failures into `URLError` so CLI commands can render graceful messages
- [x] Add regression coverage for the custom HTTPS transport path and verify with the repo test interpreter plus a direct `./pw-dev` repro

- [x] Review the bind persistence and alert path for no-op writes plus automated-test notifications
- [x] Make unchanged bind saves a true no-op with no `binds.yaml` write, no normal bind log entry, and no notification/log churn
- [x] Suppress local bind-change OS notifications during automated tests without weakening real unexpected-change alerts
- [x] Add focused regression coverage and verify with `PYTHONPATH=$PWD/python ./.venv-tests/bin/python -m pytest -q tests/test_bind.py`

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` so `pw echo` now prints a boxed top header before the existing output, showing the installed CLI version, the `Echo@Domain` action, the requested target, and the active output/sender/signing mode without changing the downstream verification flow.
- Updated `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` to lock in the new header on both concise and debug runs while preserving the existing payload, DNS, timing, and edge-hint assertions.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/echo.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so the new `pw echo` header contract is documented for future work.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_echo.py` (`14 passed`).

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/bind.py` so `save_bind()` now returns early when the canonical domain/schema already maps to the same bind UUID, which avoids rewriting `~/.pollyweb/binds.yaml` and avoids appending a normal bind audit entry for a no-op bind response.
- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/bind.py` so unexpected bind-change OS notifications are suppressed during automated pytest runs by checking the active pytest environment marker, while still raising the user-facing error and appending the `ALERT` log entry.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_bind.py` coverage for the no-op save path and for the pytest-only notification suppression, while keeping the existing real-notification branch covered through an explicit non-pytest environment override.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/bind.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so the no-op bind and quiet-pytest behavior are documented for future work.
- Verified with `PYTHONPATH=$PWD/python ./.venv-tests/bin/python -m pytest -q tests/test_bind.py` (`18 passed`).

- [x] Review the current `pw echo --debug` summary layout and identify where timing details are printed
- [x] Split echo timing into its own debug section and add a separate edge/CDN hints section with best-effort provider and PoP clues
- [x] Update echo docs/guidance and add focused regression coverage for the new debug sections
- [x] Verify with `PYTHONPATH=$PWD/python ./.venv-tests/bin/python -m pytest -q tests/test_echo.py`

- [x] Review the written `pw test` success-output contract and current implementation path
- [x] Add total-duration and latency timing to each passing `pw test` success line
- [x] Update `pw test` docs, repo guidance, and regression coverage for the new timing output
- [x] Verify with `PYTHONPATH=$PWD/python ./.venv-tests/bin/python -m pytest -q tests/test_test_command.py`

- [x] Add a root-level `pw-dev` launcher that runs the repo checkout directly
- [x] Document the root shortcut alongside the editable-install entry point
- [x] Verify the launcher from the repo root with the local test environment

- [x] Review the current published-vs-dev runtime contract and choose the smallest safe `pw-dev` entry-point shape
- [x] Add a repo-local `pw-dev` shortcut that skips the self-upgrade preflight without changing normal `pw`
- [x] Update docs and CLI-core regression coverage, then verify with the repo test interpreter

- [x] Review the written `pw echo` error-handling instructions and current debug/non-debug URLError behavior
- [x] Keep non-debug `pw echo` resolver failures graceful while surfacing the underlying transport detail in `--debug`
- [x] Add focused regression coverage and verify with the repo test interpreter

- [x] Inspect the written `pw echo` success-output contract and locate the current success print path
- [x] Add total-duration and network-latency timing to the verified `pw echo` success output
- [x] Update echo docs/tests/repo guidance for the new one-line timing output
- [x] Verify with `./.venv-tests/bin/python -m pytest -q tests/test_echo.py`

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` so `pw echo --debug` now prints timing details in a dedicated `Network timing` section and a separate `Edge / CDN hints` section that surfaces best-effort transport metadata such as request URL, HTTP status, detected CDN provider, CloudFront-style PoP values, and key edge headers when available.
- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/tools/transport.py` to capture response headers from the shared wallet send path during debug-capable calls without changing the `Wallet.send(...)` flow, so echo debug output can report edge-routing clues such as `Via`, `X-Cache`, `X-Amz-Cf-Pop`, and `X-Amz-Cf-Id`.
- Updated `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py`, `/Users/jorgemf/Git/wallet-cli/tests/cli_test_helpers.py`, `/Users/jorgemf/Git/wallet-cli/docs/commands/echo.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` to document and lock in the new debug-section layout plus the CloudFront/PoP hint behavior.
- Verified with `PYTHONPATH=$PWD/python ./.venv-tests/bin/python -m pytest -q tests/test_echo.py` (`13 passed`).

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py` so each passing `pw test` fixture now prints one concise line with total duration in milliseconds and the percentage of that time spent in the network send, reusing the shared wallet-send timing hook already exposed by the transport layer.
- Updated `/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py` to lock in the new `✅ Passed: ... (<ms> ms, <%> latency)` shape across explicit fixtures, default `pw-tests` sweeps, and debug/json variants without depending on exact clock values.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/test.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so the new `pw test` success-output contract is documented for future work.
- Verified with `PYTHONPATH=$PWD/python ./.venv-tests/bin/python -m pytest -q tests/test_test_command.py` (`30 passed, 1 skipped`).

- Added a checked-in root launcher at `/Users/jorgemf/Git/wallet-cli/pw-dev` that prefers `./.venv-tests/bin/python`, falls back to `python3` or `python`, sets `PYTHONPATH` to the repo `python` directory, and invokes `main_dev()` so local runs skip the published-runtime upgrade preflight.
- Updated `/Users/jorgemf/Git/wallet-cli/README.md`, `/Users/jorgemf/Git/wallet-cli/docs/install.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` to document the new root-level `./pw-dev` workflow.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_cli_core.py` coverage that exercises the checked-in root launcher via subprocess and confirms it does not trigger an upgrade notice.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_cli_core.py` (`35 passed`) and a direct repo-root run of `./pw-dev version` (`pw 0.1.dev143`).

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/cli.py` to split command dispatch from upgrade preflight and added a dedicated `main_dev()` path so repo-local runs can bypass the PyPI self-upgrade check without weakening normal `pw`.
- Added `pw-dev = "pollyweb_cli.cli:main_dev"` in `/Users/jorgemf/Git/wallet-cli/pyproject.toml`, which makes editable installs expose a clean `pw-dev` shortcut for development.
- Updated `/Users/jorgemf/Git/wallet-cli/tests/test_cli_core.py`, `/Users/jorgemf/Git/wallet-cli/docs/install.md`, `/Users/jorgemf/Git/wallet-cli/README.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` to document and lock in the new dev-entry-point workflow.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_cli_core.py` (`35 passed`).

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` so `pw echo` now keeps the friendly resolver guidance on the normal path while `pw echo --debug` preserves the underlying `URLError.reason` detail for low-level troubleshooting.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` coverage for the new `--debug` network-failure contract, alongside the existing non-debug graceful-error assertion.
- Updated `/Users/jorgemf/Git/wallet-cli/AGENTS.md` and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so future echo changes preserve the split between concise default messaging and verbose debug diagnostics.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_echo.py` (`12 passed`).

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` so successful `pw echo` runs now print a single verification line that includes total request-and-verification duration in milliseconds plus the percentage of that time spent in the network send, while the debug path also reports the same timing details in the verbose summary.
- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/tools/transport.py` to expose measured wallet-send wall time back to callers through an optional timing dict, keeping the shared send path reusable without changing existing call sites.
- Tightened `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` and refreshed `/Users/jorgemf/Git/wallet-cli/docs/commands/echo.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so the new output contract is documented and locked in.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_echo.py` (`11 passed`).

- [x] Fix `parse_message_request()` so long inline JSON is parsed before any filesystem existence check
- [x] Add regression coverage for `pw test` style wrapped outbound JSON that used to trigger `OSError: [Errno 63] File name too long`
- [x] Update docs/repo guidance if the user-visible behavior changed
- [x] Verify with focused pytest, then the full repo test interpreter
- [ ] Commit, push to `main`, wait for PyPI publish, upgrade `pw` in `any-buffer`, and rerun `pw test --debug`

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/msg.py` so inline JSON message arguments are parsed before any `Path.exists()` probe, preventing macOS from raising `OSError: [Errno 63] File name too long` when `pw test` serializes a wrapped `Outbound` fixture into a long JSON string.
- Added `/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py` coverage for the exact wrapped `Proxy@Domain -> Push@Buffer` fixture shape that failed in `any-buffer`, locking in both the parser behavior and the normalized `.dom` transport target.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_test_command.py` (`30 passed, 1 skipped`) and `./.venv-tests/bin/python -m pytest` (`171 passed, 1 skipped`).

- [x] Confirm the latest published `pollyweb` release and compare it with the repo floor
- [x] Run a PyPI-backed upgrade in the repo test virtualenv
- [x] Verify the repo with the required `./.venv-tests/bin/python -m pytest` command

# Review

- Upgraded the repo test virtualenv from `pollyweb 1.0.68` to the newer published PyPI release `1.0.70` with `./.venv-tests/bin/python -m pip install --upgrade pollyweb`.
- Raised the package floor in `/Users/jorgemf/Git/wallet-cli/pyproject.toml` to `pollyweb>=1.0.70`, updated wallet-backed signing to use `pollyweb.Wallet.sign(...)`, switched the domain-signed echo fixture helper to `Msg.sign_with(...)`, and updated `/Users/jorgemf/Git/wallet-cli/AGENTS.md` plus `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` to match.
- Verified the full suite against the repo source with `PYTHONPATH=$PWD/python ./.venv-tests/bin/python -m pytest` (`165 passed, 1 skipped`).

# Task Plan

- [x] Inspect the current bind-alert metadata and find the version source
- [x] Add CLI version details to bind-change alert logs and user-facing errors
- [x] Verify the updated bind alert coverage with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/bind.py` so bind-change discovery now records the installed CLI version alongside the script path in both the `ALERT` log entry and the raised `UserFacingError`.
- Updated `/Users/jorgemf/Git/wallet-cli/tests/test_bind.py` to assert the new version field is logged and surfaced in the bind-change error text.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/bind.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so the new caller-version diagnostic is documented for future work.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_bind.py` (`16 passed`).

# Task Plan

- [x] Review the current bind-alert behavior and identify where to attach caller-script diagnostics
- [x] Add the triggering script path to bind-change alert logs and user-facing errors
- [x] Verify the updated bind alert coverage with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/bind.py` so bind-change discovery now records the current top-level script path in both the `ALERT` log entry and the raised `UserFacingError`.
- Updated `/Users/jorgemf/Git/wallet-cli/tests/test_bind.py` to assert the new `script_path` field is logged and surfaced in the bind-change error text.
- Updated `/Users/jorgemf/Git/wallet-cli/docs/commands/bind.md`, `/Users/jorgemf/Git/wallet-cli/AGENTS.md`, and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so the new caller-path diagnostic is documented for future work.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_bind.py` (`16 passed`).

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

# Task Plan

- [x] Inspect the current `pw echo --debug` failure path and identify which exceptions bypass the in-app renderer
- [x] Keep debug failures inside the echo UI by rendering an explicit error summary instead of leaking a traceback
- [x] Add regression coverage for debug echo failures and verify with the repo test interpreter

# Review

- Updated `/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/echo.py` so `pw echo --debug` now catches early request-building, parsing, and other debug-path failures and renders them inside the echo UI with an `Error summary`, timing details, and the existing footer instead of leaking a top-level traceback.
- Updated `/Users/jorgemf/Git/wallet-cli/tests/test_echo.py` to lock in the new in-app debug failure summary for both request-validation failures and post-response verification failures.
- Updated `/Users/jorgemf/Git/wallet-cli/AGENTS.md` and `/Users/jorgemf/Git/wallet-cli/tasks/lessons.md` so future `pw echo --debug` work preserves the in-app failure renderer.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_echo.py` (`15 passed`).
