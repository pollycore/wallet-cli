# Task Plan

- [x] Review the written instructions, docs, and current `pw bind` implementation
- [x] Normalize bind domains before signing, transport, and local bind persistence
- [x] Replace the CLI's custom message transport with shared wallet-backed sending
- [x] Add regression coverage for `.dom` bind requests and wallet-backed command behavior
- [x] Update the docs and project notes to describe the wallet-backed transport rules
- [x] Run targeted verification for the wallet CLI command suite

# Review

- Replaced the hand-rolled sign-and-POST transport path with `pollyweb.Wallet.send()` across `bind`, `echo`, `msg`, `test`, `shell`, and `sync`.
- Normalized `.dom` aliases before bind signing, delivery, and local bind lookup/storage so `pw bind any-hoster.dom` stores and reuses the canonical PollyWeb domain.
- Aligned `pw msg` and `pw test` with wallet semantics by rejecting arbitrary domain `From` values and documenting the supported `Anonymous` or UUID sender forms.
- Verified the change with `./.venv/bin/python -m pytest -q tests/test_cli.py`.
