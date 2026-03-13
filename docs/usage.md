# Usage

Create your PollyWeb key pair:

```bash
pw config
```

This creates a new `pollyweb.KeyPair` and writes its PEM output to:

- `~/.pollyweb/private.pem`
- `~/.pollyweb/public.pem`

After creating the keys, the CLI sends an `Onboard@Notifier` message to `any-notifier.pollyweb.org` with the generated public key and prints the returned wallet ID when one is provided.

The CLI uses `KeyPair.private_pem_bytes()` and `KeyPair.public_pem_bytes()` internally, so consumers do not need to handle PEM serialization themselves.

If both key files already exist, `pw config` leaves them unchanged and exits successfully.

Overwrite an existing key pair:

```bash
pw config --force
```
