# Task Plan

- [x] Review the written instructions, docs, and current wallet-backed send behavior
- [x] Auto-upgrade wallet-backed `From: Anonymous` sends to the stored bind for the target domain
- [x] Keep bind lookup canonical so `.dom` recipients reuse the same stored bind entry
- [x] Add regression coverage for automatic bind-backed sender selection
- [x] Refresh command docs and record the lesson after verification
- [x] Run targeted verification for the updated send paths

# Review

- Wallet-backed sends now check `~/.pollyweb/binds.yaml` for the normalized target domain and use that bind UUID as `msg.From` whenever the caller omitted `From` or set it to `Anonymous`.
- If no bind exists, the CLI no longer forces `Anonymous`; it leaves sender fallback to `pollyweb.Wallet`, which still signs as `Anonymous` by default.
- Added regression coverage for automatic bind-backed sender selection on canonical and `.dom` target domains, plus the no-bind fallback path.
- Refreshed the command docs, README, AGENTS guidance, and lessons to describe the new sender-selection order.
- Verified the change with `./.venv/bin/python -m pytest -q tests/test_cli.py -k 'test_bind_ or test_msg_ or test_test_'`.
