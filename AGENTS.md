- Create a symbolic link "AGENTS-user.md" pointing to "~/AGENTS.md" if it doesn't exist.
- Read "AGENTS-user.md" for general instructions on AGENTS development.

- Read the goal.yaml file
- When answering questions about behavior, start by checking the written instructions and docs first, and be specific about what they do or do not say before using code to confirm runtime behavior.
- `pw msg <path>` accepts YAML or JSON files in either a top-level `To`/`Subject`/`Body` shape or a `Header` plus top-level `Body` shape, signs the message locally, and prints the raw synchronous response.
- `pw msg <message...>` also accepts Python files that expose a message object, raw JSON object strings, and inline `Key:Value` fields where non-header keys are collected into `Body`.
- For `pw msg`, a `To` value ending in `.dom` is normalized to `.pollyweb.org` before signing the message and building the inbox URL.
