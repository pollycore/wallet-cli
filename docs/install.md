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

After installation, confirm the CLI is available:

```bash
pw --help
pw shell --help
```
