# pw msg

Send a PollyWeb message from a YAML, JSON, or Python file:

```bash
pw msg ./message.yaml
```

The file must contain either top-level `To`, `Subject`, and optional `From`, `Schema`, `Body` fields, or a `Header` object with those same header values plus a top-level `Body` object. For Python files, define one of `MESSAGE`, `message`, `REQUEST`, `request`, or `build_message()` that returns that same object shape. The CLI sends the message with the configured wallet semantics to `https://pw.<To>/inbox` and prints the synchronous response as YAML by default.

Example file:

```yaml
To: vault.example.com
Subject: Echo@Domain
Body: {}
```

You can also pass a JSON object directly:

```bash
pw msg '{"To":"vault.example.com","Subject":"Echo@Domain","Body":{"Ping":"pong"}}'
```

Or build the message inline with `Key:Value` pairs. `To`, `Subject`, `From`, `Schema`, `Body`, and `Header` are treated as top-level fields, while any other keys are collected into `Body`. Those header field names are matched case-insensitively for inline arguments, so `to:` and `subject:` work the same as `To:` and `Subject:`:

```bash
pw msg To:any-domain.org Subject:topic@role DynamicBodyProperty:123
pw msg to:any-domain.dom subject:Echo@Domain --debug
```

For `pw msg`, domains ending in `.dom` are treated as shorthand for `.pollyweb.org`, so `To:any-domain.dom` is sent to `https://pw.any-domain.pollyweb.org/inbox` with `To: any-domain.pollyweb.org` in the signed message header.

Because the command follows wallet semantics end-to-end, `From` must be omitted, `Anonymous`, or a UUID bind value. When `From` is omitted or `Anonymous`, the CLI first checks `~/.pollyweb/binds.yaml` for a bind stored against the target domain and uses that bind UUID as `msg.From`; if no bind is stored, it falls back to `From: Anonymous`. Arbitrary domain `From` values are rejected instead of being hand-signed locally.

Use `--anonymous` to ignore any stored bind and force `From: Anonymous` for the outbound request. Use `--unsigned` to keep the selected sender but remove `Hash` and `Signature` before sending.

Use `--json` when you want the raw synchronous response instead of the default YAML formatting. On an interactive terminal, those JSON payloads keep the same raw structure but add JSON syntax colors; redirected or scripted output stays plain compact JSON. When you combine `--debug --json`, the debug payloads also print as raw JSON instead of the default YAML-style rendering.

Print the outbound payload, the full inbox URL the POST is sent to, and the inbound response body as colorized, indented YAML:

```bash
pw msg --debug ./message.yaml
```
