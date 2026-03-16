# pw config

Create your PollyWeb key pair:

```bash
pw config
```

This creates a new `pollyweb.KeyPair` and writes its PEM output to:

- `~/.pollyweb/private.pem`
- `~/.pollyweb/public.pem`
- `~/.pollyweb/config.yaml`

The generated `config.yaml` includes the default helper configuration:

```yaml
Helpers:
  Notifier: any-notifier.pollyweb.org
```

The CLI uses `KeyPair.private_pem_bytes()` and `KeyPair.public_pem_bytes()` internally, so consumers do not need to handle PEM serialization themselves.

After writing the local files, `pw config` also sends an `Onboard@Notifier` message to the configured notifier helper on a best-effort basis.

If all three files already exist, `pw config` leaves them unchanged and exits successfully.

Print the outbound and inbound notifier payloads while configuring:

```bash
pw config --debug
```

Overwrite an existing key pair:

```bash
pw config --force
```
