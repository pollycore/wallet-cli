# LLM Token Efficiency

Use this when changing CLI instructions or docs so future chats can load less context.

## Trigger

Run `./tools/audit-llm-context.sh` whenever a change touches:

- [AGENTS.md](/Users/jorgemf/Git/wallet-cli/AGENTS.md)
- anything under [docs](/Users/jorgemf/Git/wallet-cli/docs)
- [tasks/lessons.md](/Users/jorgemf/Git/wallet-cli/tasks/lessons.md)

## Working loop

1. Open only the command guide or routing doc needed for the task.
2. Make the code or doc change.
3. Run `./tools/audit-llm-context.sh`.
4. If a touched routing doc is over budget, condense it or split detail into the relevant command page in the same change.
5. If cleanup is larger than the current task should absorb, log it in [tasks/todo.md](/Users/jorgemf/Git/wallet-cli/tasks/todo.md).

## Heuristics

- Keep [AGENTS.md](/Users/jorgemf/Git/wallet-cli/AGENTS.md) focused on durable rules and links.
- Keep command-specific behavior in the matching file under [docs/commands](/Users/jorgemf/Git/wallet-cli/docs/commands).
- Keep long historical behavior notes in [tasks/lessons.md](/Users/jorgemf/Git/wallet-cli/tasks/lessons.md), not in always-read entrypoints.
