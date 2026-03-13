# pollyweb-cli

Command line wallet tooling built on top of the `pollyweb` Python package.

`pw config` creates a local key pair in `~/.pollyweb`.

`pw bind <domain>` sends a signed `Bind@Vault` request to `https://pw.<domain>/inbox` and stores the returned bind token in `~/.pollyweb/binds.yaml`.

`pw shell <domain>` opens an interactive shell that sends each command as a signed `Shell@Domain` message containing the configured bind list and the command text.

See [docs/install.md](docs/install.md) for installation and [docs/usage.md](docs/usage.md) for examples.
