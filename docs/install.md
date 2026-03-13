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

If you want to install from a local checkout of this repository instead, run the commands from the repository root. In that case, `.` means "this folder":

```bash
pipx install .
```

or:

```bash
python3 -m pip install .
```

If your system Python blocks global installs with an `externally-managed-environment` error, create a local virtual environment instead:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

For local development with the test dependencies included:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

After installation, confirm the CLI is available:

```bash
pw --help
pw shell --help
```
