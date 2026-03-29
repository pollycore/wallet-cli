- Read `/Users/jorgemf/Git/wallet-cli/AGENTS-user.md` directly.
- Read `goal.yaml`.
- Read `tasks/lessons.md` for historical learnings and maintenance gotchas.
- Keep `AGENTS.md` short; keep command behavior in `docs/commands/` and long operational history in `tasks/lessons.md`.
- When changing `AGENTS.md`, `docs/`, or `tasks/lessons.md`, run `./tools/audit-llm-context.sh` and either trim touched routing docs or log follow-up work in `tasks/todo.md`.

## Repo focus

- `wallet-cli` is the source repo for the `pw` CLI.
- Public command docs live in `docs/commands/`; usage routing lives in `docs/usage.md`.
- When answering behavior questions, check the written instructions and docs first, then confirm in code.

## Durable rules

- Wallet-backed sends should go through published `pollyweb` wallet send/sign helpers instead of custom transport code.
- Wallet-backed send commands only support `From: Anonymous` or a UUID bind value; reject arbitrary domain `From` values.
- Keep command docs, parser/dispatch wiring, focused tests, and user-facing help aligned in the same change when a CLI feature changes.
- Prefer the repo virtualenv for tests, such as `./.venv-tests/bin/python -m pytest`.
- The CLI runtime used by `pw` should come from a published PyPI release; use `pw-dev` for local checkout development.

## Docs

- Usage router: [docs/usage.md](docs/usage.md)
- Command guides: [docs/commands](docs/commands)
- Token maintenance: [docs/llm-token-efficiency.md](docs/llm-token-efficiency.md)
- Repo learnings: [tasks/lessons.md](tasks/lessons.md)
- Backlog: [tasks/todo.md](tasks/todo.md)
