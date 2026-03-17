# pw msg

Send a signed PollyWeb message loaded from a YAML or JSON file:

```bash
pw msg ./message.yaml
```

The file must contain either top-level `To`, `Subject`, and optional `From`, `Schema`, `Body` fields, or a `Header` object with those same header values plus a top-level `Body` object. The CLI signs the message with the configured wallet key, sends it to `https://pw.<To>/inbox`, and prints the raw synchronous response.

Example file:

```yaml
To: vault.example.com
Subject: Echo@Domain
Body: {}
```

Print the outbound payload, the full inbox URL the POST is sent to, and the inbound response body as colorized, indented YAML:

```bash
pw msg --debug ./message.yaml
```
