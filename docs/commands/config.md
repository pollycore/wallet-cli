# pw config

Create your PollyWeb key pair and register it with the notifier:

```bash
pw config
```

This creates a new `pollyweb.KeyPair`, calls `Onboard@Notifier`, and writes:

- `~/.pollyweb/private.pem`
- `~/.pollyweb/public.pem`
- `~/.pollyweb/config.yaml`

The generated `config.yaml` stores the notifier helper and wallet id returned by onboarding:

```yaml
Helpers:
  Notifier: any-notifier.pollyweb.org
Wallet: <wallet-uuid>
```

The CLI uses `KeyPair.private_pem_bytes()` and `KeyPair.public_pem_bytes()` internally, so consumers do not need to handle PEM serialization themselves.

If the wallet files already exist, `pw config` makes an idempotent `Onboard@Notifier` call with the same public key and expects the same wallet id back. If the notifier returns a different wallet id for the same key pair, the command fails with a drift error instead of rewriting the stored config.

Overwrite an existing key pair:

```bash
pw config --force
```
