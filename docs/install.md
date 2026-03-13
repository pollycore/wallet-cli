# Install

Install the CLI globally from PyPI with `pipx`:

```bash
pipx install pollyweb-cli
```

You can also install it globally with `pip`:

```bash
python3 -m pip install pollyweb-cli
```

The CLI depends on the `pollyweb` package for key generation and PEM export. You do not need to install or use `cryptography` serialization APIs directly when using `pw config`.

If you want to install from a local checkout of this repository instead, run the commands from the repository root. In that case, `.` means "this folder":

```bash
pipx install .
```

or:

```bash
python3 -m pip install .
```
