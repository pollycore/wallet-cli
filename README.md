# pollyweb-cli

Command line wallet tooling built on top of the `pollyweb` Python package.

## Install

Install the CLI globally from PyPI with `pipx`:

```bash
pipx install pollyweb-cli
```

You can also install it globally with `pip`:

```bash
python3 -m pip install pollyweb-cli
```

`pw config` creates a local key pair in `~/.pollyweb`.

`pw bind <domain>` sends a signed `Bind@Vault` request to `https://pw.<domain>/inbox` and stores the returned bind token in `~/.pollyweb/binds.yaml`.

`pw shell <domain>` opens an interactive shell that sends each command as a signed `Shell@Domain` message containing the configured bind list and the command text.

See [docs/install.md](docs/install.md) for more installation details and [docs/usage.md](docs/usage.md) for examples.
