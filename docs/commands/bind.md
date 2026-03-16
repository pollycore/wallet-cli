# pw bind

Bind your configured wallet to a domain:

```bash
pw bind vault.example.com
```

This sends a signed `Bind@Vault` message to `vault.example.com` with your configured public key in the body. The key is stored locally as PEM in `~/.pollyweb/public.pem`, but the outbound message sends only the compact key value without the PEM `BEGIN/END` wrapper lines.

Because `From` is now required, the bind request uses `Anonymous` until a real sender value is available, while still leaving `Schema` out.

When the domain replies with a payload like `Bind:123e4567-e89b-12d3-a456-426614174000`, the CLI stores it in `~/.pollyweb/binds.yaml` as a YAML list item with `Bind` and `Domain` fields, replacing any existing bind for that domain unless the reply includes a different `Schema`.

Print the outbound request payload, the full inbox URL the POST is sent to, and the inbound response body during bind as colorized, indented YAML:

```bash
pw bind --debug vault.example.com
```
