# Install

Install the CLI globally from PyPI with `pipx`:

```bash
pipx install pollyweb-cli
```

You can also install it globally with `pip`:

```bash
python3 -m pip install pollyweb-cli
```

The CLI pulls in its runtime dependencies from PyPI, including `pollyweb`, `PyYAML`, and `rich`. You do not need to install or use `cryptography` serialization APIs directly when using `pw config`.

This project only supports running the published PyPI build of `pollyweb-cli`. Local editable or development installs are not supported as a runtime; the CLI will replace them with the latest published release before running commands.

For local development, use an isolated test environment instead of running `pw` from an editable checkout:

```bash
python3 -m venv .venv-tests
. .venv-tests/bin/activate
python -m pip install -e '.[dev]'
./.venv-tests/bin/python -m pytest
```

That editable install also exposes a repo-local `pw-dev` entry point that skips the normal self-upgrade preflight so you can run your in-repo changes directly:

```bash
./.venv-tests/bin/pw-dev echo vault.example.com
```

From the root of this repo, you can also use the checked-in launcher directly:

```bash
./pw-dev echo vault.example.com
```

That wrapper prefers `./.venv-tests/bin/python` when present and otherwise falls back to `python3` or `python` while still running the checkout code from `./python`.

Use `pw-dev` only for local development. The published `pw` command keeps the normal PyPI-runtime enforcement and upgrade behavior.

After installation, confirm the CLI is available:

```bash
pw --help
pw shell --help
```
