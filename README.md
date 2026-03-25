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

Before running any `pw` command, the CLI checks PyPI for a newer published `pollyweb-cli` release. If it finds one, it automatically installs the newer release into the current Python environment and reruns the original `pw ...` command on the upgraded code. If the current runtime is a development, editable, or other non-PyPI install, the CLI replaces it with the latest published PyPI release before continuing.

For local development inside this repo, install the editable test environment and use `pw-dev` instead of `pw`. The `pw-dev` entry point skips that upgrade preflight so it runs your local checkout directly:

```bash
python3 -m venv .venv-tests
. .venv-tests/bin/activate
python -m pip install -e '.[dev]'
./.venv-tests/bin/pw-dev echo vault.example.com
```

There is also a root-level launcher in this repo, so from the checkout root you can simply run:

```bash
./pw-dev echo vault.example.com
```

To force an upgrade directly, run:

```bash
pw upgrade
```

This command directly installs the latest published `pollyweb-cli` release into the current Python environment.

To confirm which release is installed:

```bash
pw version
```

For more setup details, see [docs/install.md](docs/install.md).

## Quick Start

Create your local key pair:

```bash
pw onboard
```

This writes your keys to:

- `~/.pollyweb/private.pem`
- `~/.pollyweb/public.pem`

Bind your wallet to a domain:

```bash
pw bind vault.example.com ed25519
```

This sends a `Bind@Vault` request to `https://pw.vault.example.com/inbox` using the compact public-key value in the request body. `pw bind` now requires an explicit algorithm name and sends it as `Body.Algorithm`, so a typical request is `pw bind vault.example.com ed25519`. The command reuses the stored bind UUID for that domain from `~/.pollyweb/binds.yaml` when one exists and otherwise falls back to `From: Anonymous`, while still storing only the UUID portion of the returned bind token in `~/.pollyweb/binds.yaml`. Rebinding the same domain replaces the existing bind for that domain unless the server returns a different `Schema`, in which case both entries are kept. Use `--anonymous` to ignore the stored bind and force `From: Anonymous`, or `--unsigned` to remove `Hash` and `Signature` before sending.

You can also use the PollyWeb shorthand domain suffix:

```bash
pw bind any-hoster.dom ed25519
```

That alias is normalized to `any-hoster.pollyweb.org` before signing, delivery, and local bind storage.

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

This sends an `Echo@Domain` message to `https://pw.<domain>/inbox`, expects a synchronous PollyWeb message in return, verifies the reply signature using the responding domain's DKIM key, and checks that the response `From`, `To`, `Subject`, and `Correlation` values match the target domain and the original request. Use `--anonymous` to force `From: Anonymous`, or `--unsigned` to remove `Hash` and `Signature` before sending.

Send a signed message from a file:

```bash
pw msg ./message.yaml
```

This reads a YAML, JSON, or Python message definition, or you can pass a raw JSON object string or inline `Key:Value` fields. The CLI sends the message with wallet-backed sender selection to `https://pw.<To>/inbox` and prints the raw synchronous response body.

```bash
pw msg '{"To":"vault.example.com","Subject":"Echo@Domain","Body":{"Ping":"pong"}}'
pw msg To:any-domain.org Subject:topic@role DynamicBodyProperty:123
pw msg to:any-domain.dom subject:Echo@Domain --debug
```

For `pw msg`, inline header keys like `to` and `subject` are matched case-insensitively, and a `To` domain ending in `.dom` is expanded to `.pollyweb.org` before sending. `From` must be omitted, `Anonymous`, or a UUID bind value. When `From` is omitted or `Anonymous`, the CLI first checks `~/.pollyweb/binds.yaml` for a stored bind matching the target domain and uses that UUID as `msg.From`; if none is stored, it falls back to `From: Anonymous`. Use `--anonymous` to ignore stored binds entirely, or `--unsigned` to keep the selected sender but remove `Hash` and `Signature`.

Run a wrapped message test fixture:

```bash
pw test ./test.yaml
```

Or, when the current directory contains `pw-tests`, run every `*.yaml` fixture in that folder in alphabetical order:

```bash
pw test
```

This reads a YAML file with `Outbound` and optional `Inbound` sections. The CLI sends only `Outbound` with the same wallet-backed rules as `pw msg`, then if `Inbound` is present it parses the synchronous JSON response and verifies that the expected `Inbound` fields appear in the returned payload. Fixtures can also use `{BindOf(domain)}` string placeholders, which resolve against `~/.pollyweb/binds.yaml` with the same canonical domain normalization as `pw bind`. Any string field may also use `"<PublicKey>"`, which resolves to the configured wallet public key from `~/.pollyweb/public.pem` without the PEM envelope lines. Inside `Inbound`, the special strings `"<uuid>"`, `"<str>"`, and `"<int>"` match any valid UUID, present non-empty string, or integer value in the returned payload. `--anonymous` ignores stored binds, and `--unsigned` removes `Hash` and `Signature` before sending.

## Debugging Bind Requests

Use `--debug` with `pw bind` to print the outbound request payload, the full inbox URL the POST is sent to, and the inbound response body as colorized, indented YAML:

```bash
pw bind --debug vault.example.com ed25519
```

This is useful when you want to inspect the exact message contents being sent or troubleshoot an unexpected server response.

## Command Summary

- `pw onboard` generates a PollyWeb key pair in `~/.pollyweb`
- `pw onboard --force` replaces an existing key pair
- `pw bind <domain> <algorithm>` requests and stores a bind token for a domain while sending the algorithm in `Body.Algorithm`
- `pw bind --debug <domain> <algorithm>` shows the target inbox URL plus bind request and response payloads as colorized YAML
- `pw echo <domain>` sends `Echo@Domain` and verifies the signed synchronous response, accepting a reply `To` that matches either the target domain or its stored bind UUID
- `pw echo --debug <domain>` shows the target inbox URL, echo request and response payloads, and DNS/DNSSEC diagnostics for the PollyWeb branch and DKIM lookup as colorized YAML; `.dom` may be used as shorthand for `.pollyweb.org`
- `pw msg <message...>` sends a signed message from a YAML, JSON, or Python file, a JSON object string, or inline `Key:Value` fields
- `pw msg --debug <message...>` shows the target inbox URL plus message request and response payloads as colorized YAML
- `pw test [path]` sends a wrapped `Outbound` fixture and verifies the returned payload against `Inbound`
- `pw test` without a path runs every `*.yaml` fixture under `./pw-tests` in alphabetical order
- `pw test --debug [path]` shows the target inbox URL plus test request and response payloads as colorized YAML
- `pw chat` listens for AppSync Events on the configured notifier and wallet channel
- `pw chat [domain]` optionally overrides `Helpers.Notifier` for that run
- `pw chat --test` publishes a `"TEST"` event immediately after connecting, then listens
- `pw version` prints the installed CLI version after the same upgrade preflight check used by other `pw` commands

For more examples and command behavior, see [docs/usage.md](docs/usage.md) and the command-specific guides in `docs/commands/`.
