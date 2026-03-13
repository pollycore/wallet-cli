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

This sends a signed `Bind@Vault` request to `https://pw.vault.example.com/inbox` and stores the returned bind token in `~/.pollyweb/binds.yaml`.

Open an interactive shell against a domain:

```bash
pw shell vault.example.com
```

Each command you enter is sent as a signed `Shell@Domain` message that includes your configured bind list and command text.

To inspect the signed shell request and raw response for each command:

```bash
pw shell --debug vault.example.com
```

## Debugging Bind Requests

Use `--debug` with `pw bind` to print the raw outbound request payload and inbound response body:

```bash
pw bind --debug vault.example.com
```

This is useful when you want to inspect the exact signed JSON being sent or troubleshoot an unexpected server response.

## Command Summary

- `pw config` generates a PollyWeb key pair in `~/.pollyweb`
- `pw config --force` replaces an existing key pair
- `pw bind <domain>` requests and stores a bind token for a domain
- `pw bind --debug <domain>` shows bind request and response payloads
- `pw shell <domain>` starts an interactive remote shell session
- `pw shell --debug <domain>` shows shell request and response payloads

For more examples and command behavior, see [docs/usage.md](docs/usage.md).
