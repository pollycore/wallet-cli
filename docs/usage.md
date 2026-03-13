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

This sends a signed `Bind@Vault` message to `vault.example.com` with your configured public key in the body. The key is stored locally as PEM in `~/.pollyweb/public.pem`, but the outbound message sends only the compact key value without the PEM `BEGIN/END` wrapper lines. Because `From` and `Schema` are now optional on PollyWeb messages, the bind request leaves both out. When the domain replies with a payload like `Bind:123e4567-e89b-12d3-a456-426614174000`, the CLI stores it in `~/.pollyweb/binds.yaml` as a YAML list item with `Bind` and `Domain` fields, replacing any existing bind for that domain unless the reply includes a different `Schema`.

To print the outbound request payload and inbound response body during bind as colorized, indented YAML:

```bash
pw bind --debug vault.example.com
```

Open an interactive shell against a domain:

```bash
pw shell vault.example.com
```

This starts a prompt like `pw:vault.example.com> `. Each command you enter is parsed with standard shell token rules and sent to `vault.example.com` as a signed `Shell@Domain` message whose `From` header is set to the first stored bind for that domain, while the body contains the base command and an argument dictionary:

```yaml
Command: send
Arguments:
  amount: "10"
  user: alice
  "0": bob
```

Inputs like `--amount 10` become `amount: "10"`, short flags like `-n 5` become `n: "5"`, and `user=alice` becomes `user: alice`. Plain positional arguments that do not match those patterns stay in `Arguments` as indexed entries such as `"0": bob`. Shell mode requires a stored bind for the target domain and will ask you to run `pw bind <domain>` first if none exists. The CLI prints the response body and waits for the next command. Empty commands are ignored. Shell mode exits when you press `Ctrl+D`, press `Ctrl+C`, or when a request error occurs.

Shell mode also stores the last 20 non-blank commands for that exact domain in `~/.pollyweb/history/<domain>.txt` and loads them when the session starts, so the terminal's up/down arrows can navigate recent commands for that domain only. Commands are written to history before the request is sent, so even a command that fails on the server is still available in history.

To print the outbound request payload and inbound response body for each shell command as colorized, indented YAML:

```bash
pw shell --debug vault.example.com
```
