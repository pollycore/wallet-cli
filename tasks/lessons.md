# Lessons

- When `pw bind` receives a `Bind:<UUID>` response, keep the prefix in wire parsing only and normalize persisted values to the bare UUID so `binds.yaml` stays clean and `pw shell` can still derive the sender value from either format.
- When a CLI command in this repo is acting as a wallet, prefer `pollyweb.Wallet.send()` over custom signing, `urllib` request code, or manual inbox POST helpers so `.dom` alias normalization, message shape, and wallet semantics stay aligned with the published library.
- If a command is wallet-backed, treat `From` as wallet identity, not an arbitrary sender override: accept `Anonymous` or a UUID bind value, and reject domain `From` values early.
- If the server scopes bind allocation by domain, `pw bind` must send the normalized target domain in `Body.Domain`, not just the public key, or multiple domains can still collapse into one bind pool.
- Treat "check for a newer `pw` before `pw bind`, ask before upgrading, and remember declines" as user-facing behavior/instructions, not as something the CLI itself should implement.
- When following the user's `pw bind` workflow, compare the invoked local `pw --version` against the latest published release and treat dev builds like `0.1.dev43` as older than stable releases like `0.1.61`; if the published release is newer, ask before running the command.
- For automatic `pw` upgrade prompts, run the preflight before every `pw` invocation, including `pw --version`, and read the latest release from the PyPI JSON metadata endpoint with cache-busting headers instead of trusting the rendered HTML page.
- When upgrading `pollyweb` in an older local virtualenv, follow the package upgrade with `python -m pip install -e '.[dev]'` in that env so stale editable-install metadata does not keep pinning an older exact `pollyweb` version.
- For wallet-backed sends, the CLI should only override `msg.From` when it has something concrete to provide, such as a stored bind UUID for the target domain; otherwise let `pollyweb.Wallet` apply its own default `Anonymous` sender.
