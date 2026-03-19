# pw bind

Bind your configured wallet to a domain:

```bash
pw bind vault.example.com
```

This sends a `Bind@Vault` message to `vault.example.com` with your configured public key in the body. The key is stored locally as PEM in `~/.pollyweb/public.pem`, but the outbound message sends only the compact key value without the PEM `BEGIN/END` wrapper lines.

By default, the request uses a stored bind UUID from `~/.pollyweb/binds.yaml` when one already exists for that target domain; otherwise it falls back to `From: Anonymous`. The request also includes the standard PollyWeb schema header.

Domains ending in `.dom` are normalized to `.pollyweb.org` before the message is signed and sent, so `pw bind any-hoster.dom` targets `https://pw.any-hoster.pollyweb.org/inbox` and stores the canonical domain name locally.

Before loading keys or attempting transport, `pw bind` now validates the normalized target domain using the same PollyWeb message rules as other outbound requests. Malformed values such as `bad domain.com`, `a..b.com`, or bare names without a valid domain shape fail immediately with a direct user error instead of falling through to a generic command failure. If the normalized inbox host still cannot be translated by DNS, the command should report that as a readable `Could not resolve PollyWeb inbox host pw.<domain>` error instead of leaking a raw resolver traceback or the generic unexpected-failure message.

When the domain replies with a payload like `123e4567-e89b-12d3-a456-426614174000`, the CLI stores that UUID in `~/.pollyweb/binds.yaml` as a YAML list item with `Bind` and `Domain` fields. If the same domain and schema already have a different stored bind UUID, the CLI now raises an error instead of replacing it so unexpected bind churn can be investigated. Distinct `Schema` values are still stored as separate entries. The legacy `Bind:<UUID>` response format is still accepted for compatibility.

Each effective `pw bind` write also appends a wallet-managed audit entry to `~/.pollyweb/binds.log`. If the same canonical domain and schema already point at the same bind UUID, the CLI now treats that as a no-op and leaves both `~/.pollyweb/binds.yaml` and `~/.pollyweb/binds.log` untouched. Unexpected bind changes still append an `ALERT` entry including the detected top-level script path and CLI version that triggered the change attempt, and on macOS the CLI attempts to raise a local notification outside automated pytest runs so test suites stay quiet.

Use `--anonymous` to ignore any stored bind and force `From: Anonymous`. Use `--unsigned` to remove `Hash` and `Signature` before sending.

Print the outbound request payload, the full inbox URL the POST is sent to, and the inbound response body during bind as colorized, indented YAML:

```bash
pw bind --debug vault.example.com
```
