# Lessons

- When `pw bind` receives a `Bind:<UUID>` response, keep the prefix in wire parsing only and normalize persisted values to the bare UUID so `binds.yaml` stays clean and `pw shell` can still derive the sender value from either format.
- When a CLI command in this repo is acting as a wallet, prefer `pollyweb.Wallet.send()` over custom signing or manual inbox POST code so `.dom` alias normalization and wallet semantics stay aligned with the published library.
