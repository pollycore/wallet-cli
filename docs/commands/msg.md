# pw msg

Send a signed PollyWeb message from a YAML, JSON, or Python file:

```bash
pw msg ./message.yaml
```

The file must contain either top-level `To`, `Subject`, and optional `From`, `Schema`, `Body` fields, or a `Header` object with those same header values plus a top-level `Body` object. For Python files, define one of `MESSAGE`, `message`, `REQUEST`, `request`, or `build_message()` that returns that same object shape. The CLI signs the message with the configured wallet key, sends it to `https://pw.<To>/inbox`, and prints the raw synchronous response.

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

Or build the message inline with `Key:Value` pairs. `To`, `Subject`, `From`, `Schema`, `Body`, and `Header` are treated as top-level fields, while any other keys are collected into `Body`:

```bash
pw msg To:any-domain.org Subject:topic@role DynamicBodyProperty:123
```

For `pw msg`, domains ending in `.dom` are treated as shorthand for `.pollyweb.org`, so `To:any-domain.dom` is sent to `https://pw.any-domain.pollyweb.org/inbox` with `To: any-domain.pollyweb.org` in the signed message header.

Print the outbound payload, the full inbox URL the POST is sent to, and the inbound response body as colorized, indented YAML:

```bash
pw msg --debug ./message.yaml
```
