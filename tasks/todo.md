# Task Plan

- [x] Review the written instructions, docs, and current `pw test` fixture behavior
- [x] Add `{BindOf(<domain>)}` fixture substitution backed by `~/.pollyweb/binds.yaml`
- [x] Keep bind lookup canonical so `.dom` placeholders resolve the same stored bind
- [x] Add regression coverage and refresh the `pw test` docs
- [x] Run targeted verification for the `pw test` command path

# Review

- `pw test` now resolves `{BindOf(domain)}` placeholders anywhere in wrapped fixtures before request parsing and inbound assertions.
- Bind placeholder lookups reuse the canonical bind-domain normalization, so `.dom` aliases and `.pollyweb.org` domains resolve the same stored bind.
- Added regression coverage for direct bind placeholders, `.dom` placeholder aliases, and missing-bind errors.
- Verified the change with `./.venv/bin/python -m pytest -q tests/test_cli.py`.
