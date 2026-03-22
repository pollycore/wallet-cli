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

`Helpers.Notifier` is the domain of the PollyWeb Notifier service. Before any wallet-backed send (other than `Listen@Notifier` itself), the CLI contacts this domain to obtain a `Channel` UUID, subscribes to an AppSync WebSocket on the wallet channel, and attaches the `Channel` to the outbound message header. If the server replies with `Meta.Code: 202`, the CLI waits for the final response to arrive over the WebSocket. This enables long-running or asynchronous server-side handlers while keeping the CLI experience synchronous from the user's perspective.

The CLI uses `KeyPair.private_pem_bytes()` and `KeyPair.public_pem_bytes()` internally, so consumers do not need to handle PEM serialization themselves.

After writing the local files, `pw config` also sends an `Onboard@Notifier` message to the configured notifier helper on a best-effort basis.
When the notifier response includes a `Broker`, the CLI stores it in `~/.pollyweb/config.yaml` as `Helpers.Broker`.
When the notifier response includes a `Wallet`, the CLI stores it in `~/.pollyweb/config.yaml` as `Wallet`.

If all three files already exist, `pw config` leaves them unchanged and exits successfully.

Print the outbound and inbound notifier payloads while configuring:

```bash
pw config --debug
```

Overwrite an existing key pair:

```bash
pw config --force
```
