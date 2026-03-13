# Usage

Create your PollyWeb key pair:

```bash
pw config
```

This creates a new `pollyweb.KeyPair` and writes its PEM output to:

- `~/.pollyweb/private.pem`
- `~/.pollyweb/public.pem`

The CLI uses `KeyPair.private_pem_bytes()` and `KeyPair.public_pem_bytes()` internally, so consumers do not need to handle PEM serialization themselves.

If both key files already exist, `pw config` leaves them unchanged and exits successfully.

Overwrite an existing key pair:

```bash
pw config --force
```
