# Lessons

- When `pw bind` receives a `Bind:<UUID>` response, keep the prefix in wire parsing only and normalize persisted values to the bare UUID so `binds.yaml` stays clean and `pw shell` can still derive the sender value from either format.
- When PollyWeb already exposes the right wallet transport, prefer `pollyweb.Wallet.send()` over custom signing and `urllib` request code so `.dom` normalization and message shape stay consistent with the library.
- If a command is wallet-backed, treat `From` as wallet identity, not an arbitrary sender override: accept `Anonymous` or a UUID bind value, and reject domain `From` values early.
- When a CLI command in this repo is acting as a wallet, prefer `pollyweb.Wallet.send()` over custom signing or manual inbox POST code so `.dom` alias normalization and wallet semantics stay aligned with the published library.
- If the server scopes bind allocation by domain, `pw bind` must send the normalized target domain in `Body.Domain`, not just the public key, or multiple domains can still collapse into one bind pool.
- Treat "check for a newer `pw` before `pw bind`, ask before upgrading, and remember declines" as user-facing behavior/instructions, not as something the CLI itself should implement.
