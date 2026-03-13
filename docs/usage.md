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

Bind your configured wallet to a domain:

```bash
pw bind vault.example.com
```

This sends a signed `Bind@Vault` message to `vault.example.com` with your configured public key in the body. When the domain replies with a payload like `Bind:123e4567-e89b-12d3-a456-426614174000`, the CLI appends it to `~/.pollyweb/binds.yaml` as a YAML list item with `Bind` and `Domain` fields.

Open an interactive shell against a domain:

```bash
pw shell vault.example.com
```

This starts a prompt like `pw:vault.example.com> `. Each command you enter is sent to `vault.example.com` as a signed `Shell@Domain` message whose body contains your configured bind list and the command text:

```yaml
Binds:
  - Bind: Bind:123e4567-e89b-12d3-a456-426614174000
    Domain: vault.example.com
Command: balance
```

The CLI prints the response body and waits for the next command. Empty commands are ignored. Shell mode exits when you press `Ctrl+D`, press `Ctrl+C`, or when a request error occurs.
