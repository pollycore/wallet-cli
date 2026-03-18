# pw bind

Bind your configured wallet to a domain:

```bash
pw bind vault.example.com
```

This sends a `Bind@Vault` message to `vault.example.com` with your configured public key in the body. The key is stored locally as PEM in `~/.pollyweb/public.pem`, but the outbound message sends only the compact key value without the PEM `BEGIN/END` wrapper lines.

By default, the request uses a stored bind UUID from `~/.pollyweb/binds.yaml` when one already exists for that target domain; otherwise it falls back to `From: Anonymous`. The request also includes the standard PollyWeb schema header.

Domains ending in `.dom` are normalized to `.pollyweb.org` before the message is signed and sent, so `pw bind any-hoster.dom` targets `https://pw.any-hoster.pollyweb.org/inbox` and stores the canonical domain name locally.

When the domain replies with a payload like `123e4567-e89b-12d3-a456-426614174000`, the CLI stores that UUID in `~/.pollyweb/binds.yaml` as a YAML list item with `Bind` and `Domain` fields, replacing any existing bind for that domain unless the reply includes a different `Schema`. The legacy `Bind:<UUID>` response format is still accepted for compatibility.

Use `--anonymous` to ignore any stored bind and force `From: Anonymous`. Use `--unsigned` to remove `Hash` and `Signature` before sending.

Print the outbound request payload, the full inbox URL the POST is sent to, and the inbound response body during bind as colorized, indented YAML:

```bash
pw bind --debug vault.example.com
```
