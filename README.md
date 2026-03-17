# pollyweb-cli

`pollyweb-cli` provides the `pw` command, a small wallet-style CLI built on top of the [`pollyweb`](https://pypi.org/project/pollyweb/) Python package.

It helps you:

- create a local PollyWeb key pair
- bind that identity to a PollyWeb-enabled domain
- send an echo request to a domain and verify the signed reply
- send a signed PollyWeb message from a file
- listen for notifier chat events over AppSync Events
- send signed shell commands to a remote domain

## Install

Install the CLI globally from PyPI with `pipx`:

```bash
pipx install pollyweb-cli
```

Or install it globally with `pip`:

```bash
python3 -m pip install pollyweb-cli
```

After installation, the CLI is available as:

```bash
pw --help
```

To confirm which release is installed:

```bash
pw --version
```

For more setup details, see [docs/install.md](docs/install.md).

## Quick Start

Create your local key pair:

```bash
pw config
```

This writes your keys to:

- `~/.pollyweb/private.pem`
- `~/.pollyweb/public.pem`

Bind your wallet to a domain:

```bash
pw bind vault.example.com
```

This sends a signed `Bind@Vault` request to `https://pw.vault.example.com/inbox` using the compact public-key value in the request body. The command now uses `pollyweb.Wallet.send()` directly, so when there is no wallet-specific sender yet it sends `From: Anonymous` with the standard PollyWeb schema and stores only the UUID portion of the returned bind token in `~/.pollyweb/binds.yaml`. Rebinding the same domain replaces the existing bind for that domain unless the server returns a different `Schema`, in which case both entries are kept.

You can also use the PollyWeb shorthand domain suffix:

```bash
pw bind any-hoster.dom
```

That alias is normalized to `any-hoster.pollyweb.org` before signing, delivery, and local bind storage.

Open an interactive shell against a domain:

```bash
pw shell vault.example.com
```

Listen for notifier chat events on the configured wallet channel:

```bash
pw chat
```

Override the configured notifier for a single chat session:

```bash
pw chat notifier.example.com --debug --test
```

Publish a one-shot `"TEST"` event immediately after the websocket connection is acknowledged, then keep listening:

```bash
pw chat --test
```

Send a one-shot echo request and verify the synchronous signed response:

```bash
pw echo vault.example.com
```

This sends a signed `Echo@Domain` message to `https://pw.<domain>/inbox`, expects a synchronous PollyWeb message in return, verifies the reply signature using the responding domain's DKIM key, and checks that the response `From`, `To`, `Subject`, and `Correlation` values match the target domain and the original request.

Send a signed message from a file:

```bash
pw msg ./message.yaml
```

This reads a YAML, JSON, or Python message definition, or you can pass a raw JSON object string or inline `Key:Value` fields. The CLI signs the message with the configured wallet key through `pollyweb.Wallet.send()`, sends it to `https://pw.<To>/inbox`, and prints the raw synchronous response body.

```bash
pw msg '{"To":"vault.example.com","Subject":"Echo@Domain","Body":{"Ping":"pong"}}'
pw msg To:any-domain.org Subject:topic@role DynamicBodyProperty:123
pw msg to:any-domain.dom subject:Echo@Domain --debug
```

For `pw msg`, inline header keys like `to` and `subject` are matched case-insensitively, and a `To` domain ending in `.dom` is expanded to `.pollyweb.org` before signing and sending. Because the command now follows wallet semantics directly, `From` must be omitted, `Anonymous`, or a UUID bind value.

Run a wrapped message test fixture:

```bash
pw test ./test.yaml
```

This reads a YAML file with `Outbound` and optional `Inbound` sections. The CLI sends only `Outbound` with the same wallet-backed rules as `pw msg`, then if `Inbound` is present it parses the synchronous JSON response and verifies that the expected `Inbound` fields appear in the returned payload.

Each command you enter is parsed into a base `Command` plus an `Arguments` dictionary, then sent as a signed `Shell@Domain` message whose `From` header is set to the first stored bind for that domain. Long flags like `--all 123` become `{"all":"123"}`, short flags like `-a 123` become `{"a":"123"}`, `key=value` tokens like `a=123` become `{"a":"123"}`, and plain positional arguments remain indexed as `{"0":"value"}`. `pw shell` also keeps the last 20 commands for that exact domain in `~/.pollyweb/history/`, so you can use the up/down arrows to revisit recent commands. Commands are recorded before the network request is sent, which means failed requests still appear in that domain's history.

To inspect the signed shell request and response for each command as colorized, indented YAML, including the full inbox URL the POST is sent to:

```bash
pw shell --debug vault.example.com
```

## Debugging Bind Requests

Use `--debug` with `pw bind` to print the outbound request payload, the full inbox URL the POST is sent to, and the inbound response body as colorized, indented YAML:

```bash
pw bind --debug vault.example.com
```

This is useful when you want to inspect the exact message contents being sent or troubleshoot an unexpected server response.

## Command Summary

- `pw config` generates a PollyWeb key pair in `~/.pollyweb`
- `pw config --force` replaces an existing key pair
- `pw bind <domain>` requests and stores a bind token for a domain
- `pw bind --debug <domain>` shows the target inbox URL plus bind request and response payloads as colorized YAML
- `pw echo <domain>` sends `Echo@Domain` and verifies the signed synchronous response
- `pw echo --debug <domain>` shows the target inbox URL plus echo request and response payloads as colorized YAML
- `pw msg <message...>` sends a signed message from a YAML, JSON, or Python file, a JSON object string, or inline `Key:Value` fields
- `pw msg --debug <message...>` shows the target inbox URL plus message request and response payloads as colorized YAML
- `pw test <path>` sends a wrapped `Outbound` fixture and verifies the returned payload against `Inbound`
- `pw test --debug <path>` shows the target inbox URL plus test request and response payloads as colorized YAML
- `pw chat` listens for AppSync Events on the configured notifier and wallet channel
- `pw chat [domain]` optionally overrides `Helpers.Notifier` for that run
- `pw chat --test` publishes a `"TEST"` event immediately after connecting, then listens
- `pw shell <domain>` starts an interactive remote shell session
- `pw shell <domain>` remembers the last 20 commands per domain for arrow-key navigation
- `pw shell --debug <domain>` shows the target inbox URL plus shell request and response payloads as colorized YAML
- `pw --version` prints the installed CLI version

For more examples and command behavior, see [docs/usage.md](docs/usage.md) and the command-specific guides in `docs/commands/`.
