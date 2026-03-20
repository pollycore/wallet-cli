# Task Plan

- [x] Inspect the `Proxy@Domain` nested-message send path and current error wording
- [x] Normalize proxied nested headers so extra fields do not fail transport validation while `To` and `Subject` stay required
- [x] Rewrite backend validation paths into user-facing outbound paths for HTTP error output
- [x] Add focused regression coverage and verify with the repo test interpreter

# Review

- Updated [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/tools/transport.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/tools/transport.py) so `Proxy@Domain` requests now normalize nested proxied headers down to the required `To` and `Subject` keys before send, which lets user-authored extra fields like `From` stop causing backend validation failures.
- Updated [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/tools/transport.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/tools/transport.py) and [/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py](/Users/jorgemf/Git/wallet-cli/python/pollyweb_cli/features/test.py) so backend validation paths such as `Body.Message.Header` are rewritten into the user-facing outbound fixture path `Outbound.Body.Header` in debug payloads and concise HTTP error output.
- Added regression coverage in [/Users/jorgemf/Git/wallet-cli/tests/test_msg_command.py](/Users/jorgemf/Git/wallet-cli/tests/test_msg_command.py) and [/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py](/Users/jorgemf/Git/wallet-cli/tests/test_test_command.py) for proxy-header sanitization, required nested routing keys, and rewritten backend validation paths.
- Verified with `./.venv-tests/bin/python -m pytest -q tests/test_msg_command.py tests/test_test_command.py`.
