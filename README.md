# pollyweb-cli

`pollyweb-cli` provides the `pw` command, a small wallet-style CLI built on top of the [`pollyweb`](https://pypi.org/project/pollyweb/) Python package.

It helps you:

- create a local PollyWeb key pair
- bind that identity to a PollyWeb-enabled domain
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

This sends a signed `Bind@Vault` request to `https://pw.vault.example.com/inbox` using the compact public-key value in the request body. The bind request now relies on PollyWeb's optional message fields, so it omits explicit `From` and `Schema` values, and stores the returned bind token in `~/.pollyweb/binds.yaml`. Rebinding the same domain replaces the existing bind for that domain unless the server returns a different `Schema`, in which case both entries are kept.

Open an interactive shell against a domain:

```bash
pw shell vault.example.com
```

Each command you enter is parsed into a base `Command` plus an `Arguments` dictionary, then sent as a signed `Shell@Domain` message whose `From` header is set to the first stored bind for that domain. Long flags like `--all 123` become `{"all":"123"}`, short flags like `-a 123` become `{"a":"123"}`, `key=value` tokens like `a=123` become `{"a":"123"}`, and plain positional arguments remain indexed as `{"0":"value"}`. `pw shell` also keeps the last 20 commands for that exact domain in `~/.pollyweb/history/`, so you can use the up/down arrows to revisit recent commands. Commands are recorded before the network request is sent, which means failed requests still appear in that domain's history.

To inspect the signed shell request and response for each command as colorized, indented YAML:

```bash
pw shell --debug vault.example.com
```

## Debugging Bind Requests

Use `--debug` with `pw bind` to print the outbound request payload and inbound response body as colorized, indented YAML:

```bash
pw bind --debug vault.example.com
```

This is useful when you want to inspect the exact message contents being sent or troubleshoot an unexpected server response.

## Command Summary

- `pw config` generates a PollyWeb key pair in `~/.pollyweb`
- `pw config --force` replaces an existing key pair
- `pw bind <domain>` requests and stores a bind token for a domain
- `pw bind --debug <domain>` shows bind request and response payloads as colorized YAML
- `pw shell <domain>` starts an interactive remote shell session
- `pw shell <domain>` remembers the last 20 commands per domain for arrow-key navigation
- `pw shell --debug <domain>` shows shell request and response payloads as colorized YAML
- `pw --version` prints the installed CLI version

For more examples and command behavior, see [docs/usage.md](docs/usage.md).
