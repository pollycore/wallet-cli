"""CLI entrypoint that wires together the feature modules."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as get_installed_version
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib

from packaging.version import InvalidVersion, Version
import yaml
from pollyweb import KeyPair, Msg
import pollyweb.msg as pollyweb_msg
from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text

import pollyweb_cli.features.bind as bind_feature
import pollyweb_cli.features.chat as chat_feature
import pollyweb_cli.features.config as config_feature
import pollyweb_cli.tools.debug as debug_tools
import pollyweb_cli.features.echo as echo_feature
import pollyweb_cli.features.sync as sync_feature
import pollyweb_cli.features.test as test_feature
from pollyweb_cli.features.bind import (
    BIND_PATTERN,
    BIND_SCHEMA_KEY,
    BIND_SUBJECT,
    cmd_bind as _cmd_bind,
    get_first_bind_for_domain,
    load_binds,
    save_bind,
    send_bind_message,
    serialize_public_key_value,
)
from pollyweb_cli.features.chat import (
    cmd_chat as _cmd_chat,
)
from pollyweb_cli.features.config import (
    cmd_config as _cmd_config,
    load_signing_key_pair as _load_signing_key_pair,
    NOTIFIER_DOMAIN,
    NOTIFIER_LANGUAGE,
    NOTIFIER_SUBJECT,
    require_configured_keys as _require_configured_keys,
    send_onboard_message as _send_onboard_message_impl,
)
from pollyweb_cli.tools.debug import (
    DEBUG_CONSOLE,
    DEBUG_KEY_STYLE,
    DEBUG_LITERAL_KEYS,
    DEBUG_LITERAL_STYLE,
    DEBUG_PUNCTUATION_STYLE,
    DEBUG_VALUE_STYLE,
    DEBUG_WRAP_WIDTH,
    HTTP_CODE_STYLES,
    SHELL_CONSOLE,
    extract_http_code as _extract_http_code_impl,
    get_http_code_style as _get_http_code_style_impl,
    parse_debug_payload as _parse_debug_payload_impl,
    parse_shell_response_body as _parse_shell_response_body_impl,
    print_debug_payload,
    print_echo_response,
    print_shell_response,
    render_debug_yaml as _render_debug_yaml_impl,
)
from pollyweb_cli.features.echo import (
    ECHO_SUBJECT,
    EchoResponse,
    cmd_echo as _cmd_echo,
    parse_and_verify_echo_response,
)
from pollyweb_cli.features.msg import (
    cmd_msg as _cmd_msg,
)
from pollyweb_cli.features.test import (
    cmd_test as _cmd_test,
)
from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.parser import build_parser as _build_parser
from pollyweb_cli.features.shell import (
    SHELL_HISTORY_LIMIT,
    SHELL_SUBJECT,
    build_shell_arguments,
    cmd_shell as _cmd_shell,
    configure_shell_history,
    get_shell_from_value,
    get_shell_history_path,
    is_shell_exit_command,
    load_shell_history,
    parse_shell_command,
    record_shell_history,
    save_shell_history,
)
from pollyweb_cli.features.sync import (
    SYNC_SUBJECT,
    build_sync_files_map as _build_sync_files_map,
    cmd_sync as _cmd_sync,
)

try:
    import readline
except ImportError:  # pragma: no cover - platform-dependent fallback
    readline = None


CONFIG_DIR = Path.home() / ".pollyweb"
PRIVATE_KEY_PATH = CONFIG_DIR / "private.pem"
PUBLIC_KEY_PATH = CONFIG_DIR / "public.pem"
CONFIG_PATH = CONFIG_DIR / "config.yaml"
BINDS_PATH = CONFIG_DIR / "binds.yaml"
HISTORY_DIR = CONFIG_DIR / "history"
SYNC_DIR = CONFIG_DIR / "sync"
ERROR_STYLE = "\033[1;31m"
ERROR_STYLE_RESET = "\033[0m"
PACKAGE_NAME = "pollyweb-cli"
PYPI_JSON_URL = f"https://pypi.org/pypi/{PACKAGE_NAME}/json"
SKIP_UPGRADE_CHECK_ENV = "POLLYWEB_CLI_SKIP_UPGRADE_CHECK"
UPGRADE_CONSOLE = Console(stderr = True)


def build_parser():
    """Build the top-level argument parser for the CLI."""

    return _build_parser(_get_cli_version)


def _sync_runtime_dependencies() -> None:
    """Propagate facade-level monkeypatches into the split feature modules."""

    debug_tools.DEBUG_CONSOLE = DEBUG_CONSOLE
    debug_tools.SHELL_CONSOLE = SHELL_CONSOLE
    bind_feature.yaml = yaml
    config_feature.send_onboard_message = send_onboard_message


def print_error(message: str) -> None:
    """Print a concise error, with color when stderr is interactive."""

    if sys.stderr.isatty():
        print(f"{ERROR_STYLE}{message}{ERROR_STYLE_RESET}", file=sys.stderr)
        return
    print(message, file=sys.stderr)


def _get_cli_version() -> str:
    """Resolve the installed package version for `pw version`."""

    try:
        return get_installed_version(PACKAGE_NAME)
    except PackageNotFoundError:
        return "0+unknown"


def _get_latest_published_version() -> str | None:
    """Fetch the latest published package version from PyPI metadata."""

    request = urllib.request.Request(
        f"{PYPI_JSON_URL}?_={int(time.time())}",
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return None
    info = payload.get("info")
    if not isinstance(info, dict):
        return None
    version = info.get("version")
    return str(version) if version else None


def _parse_version(value: str) -> Version | None:
    """Parse a PEP 440 version, returning None when parsing fails."""

    try:
        return Version(value)
    except InvalidVersion:
        return None


def _install_upgrade(
    installed_version: str,
    latest_version: str,
    *,
    quiet: bool = False,
) -> bool:
    """Install the requested release and report whether the install succeeded."""

    install_target = f"{PACKAGE_NAME}=={latest_version}"

    # Keep automatic upgrades quiet so the command flow stays focused.
    command = [sys.executable, "-m", "pip", "install", "-U", install_target]
    run_kwargs: dict[str, object] = {"check": False}
    if quiet:
        run_kwargs["stdout"] = subprocess.DEVNULL
        run_kwargs["stderr"] = subprocess.DEVNULL

    result = subprocess.run(
        command,
        **run_kwargs,
    )
    if result.returncode == 0:
        return True

    print_error(
        f"Notice: Failed to upgrade {PACKAGE_NAME} to {latest_version}; "
        f"continuing with installed {installed_version}."
    )
    return False


def _upgrade_and_restart(
    argv: list[str],
    installed_version: str,
    latest_version: str,
) -> int | None:
    """Install the requested release into the current environment and re-exec."""

    upgrade_message = f"Upgrading from v{installed_version} to v{latest_version}"
    upgraded_message = f"ℹ️ Upgrade from from v{installed_version} to v{latest_version}"

    if sys.stderr.isatty():
        with UPGRADE_CONSOLE.status(
            upgrade_message,
            spinner = "dots",
            transient = True,
        ):
            installed = _install_upgrade(
                installed_version,
                latest_version,
                quiet = True,
            )
    else:
        installed = _install_upgrade(
            installed_version,
            latest_version,
            quiet = True,
        )

    if not installed:
        return None

    print(upgraded_message, file = sys.stderr)

    restart_env = os.environ.copy()
    restart_env[SKIP_UPGRADE_CHECK_ENV] = "1"
    os.execve(
        sys.executable,
        [sys.executable, "-m", "pollyweb_cli.cli", *argv],
        restart_env,
    )
    return 0


def _maybe_upgrade_before_command(argv: list[str]) -> int | None:
    """Upgrade before any `pw` command when a newer release exists."""

    if os.environ.get(SKIP_UPGRADE_CHECK_ENV) == "1":
        return None

    installed_version = _get_cli_version()
    latest_version = _get_latest_published_version()
    if not latest_version:
        return None

    installed = _parse_version(installed_version)
    latest = _parse_version(latest_version)
    if installed is None or latest is None or latest <= installed:
        return None

    return _upgrade_and_restart(
        argv,
        installed_version,
        latest_version,
    )


def cmd_upgrade() -> int:
    """Force-install the latest published CLI release."""

    installed_version = _get_cli_version()
    latest_version = _get_latest_published_version()
    if not latest_version:
        print_error(
            f"Error: Could not determine the latest published {PACKAGE_NAME} release."
        )
        return 1

    if not _install_upgrade(installed_version, latest_version):
        return 1

    print(f"Upgraded {PACKAGE_NAME} from {installed_version} to {latest_version}.")
    return 0


def cmd_version() -> int:
    """Print the installed CLI version."""

    print(f"pw {_get_cli_version()}")
    return 0


def require_configured_keys() -> None:
    """Ensure the local wallet keypair exists."""

    _require_configured_keys(CONFIG_DIR, PRIVATE_KEY_PATH, PUBLIC_KEY_PATH)


def load_signing_key_pair() -> KeyPair:
    """Load the configured wallet private key as a PollyWeb keypair."""

    return _load_signing_key_pair(PRIVATE_KEY_PATH)


def _parse_debug_payload(payload: str) -> object:
    """Compatibility wrapper for debug payload parsing."""

    return _parse_debug_payload_impl(payload)


def _extract_http_code(payload: str) -> int | None:
    """Compatibility wrapper for HTTP-style code extraction."""

    return _extract_http_code_impl(payload)


def _get_http_code_style(code: int) -> str | None:
    """Compatibility wrapper for code-style mapping."""

    return _get_http_code_style_impl(code)


def _parse_shell_response_body(payload: str) -> tuple[str | None, str | None]:
    """Compatibility wrapper for shell response parsing."""

    return _parse_shell_response_body_impl(payload)


def _render_debug_yaml(yaml_payload: str):
    """Compatibility wrapper for debug YAML rendering."""

    return _render_debug_yaml_impl(yaml_payload)


def print_shell_response(payload: str) -> None:
    """Render a shell response using the currently configured shell console."""

    _sync_runtime_dependencies()
    debug_tools.print_shell_response(payload)


def print_echo_response(payload: str) -> None:
    """Render an echo response using the currently configured debug console."""

    _sync_runtime_dependencies()
    debug_tools.print_echo_response(payload)


def send_onboard_message(
    key_pair: KeyPair,
    public_key: bytes,
    notifier_domain: str,
    debug: bool = False
) -> dict[str, object]:
    """Send the onboarding request using the compatibility facade."""

    return _send_onboard_message_impl(
        key_pair,
        public_key,
        notifier_domain,
        debug=debug,
    )


def build_sync_files_map(domain: str) -> dict[str, dict[str, str]]:
    """Build the sync file map using the configured sync directory."""

    return _build_sync_files_map(domain, SYNC_DIR)


def cmd_config(
    force: bool,
    debug: bool = False
) -> int:
    """Run the configuration command with the current filesystem paths."""

    _sync_runtime_dependencies()
    return _cmd_config(
        force=force,
        debug=debug,
        config_dir=CONFIG_DIR,
        private_key_path=PRIVATE_KEY_PATH,
        public_key_path=PUBLIC_KEY_PATH,
        config_path=CONFIG_PATH,
    )


def cmd_bind(
    domain: str,
    debug: bool = False,
    unsigned: bool = False,
    anonymous: bool = False
) -> int:
    """Run the bind command with the current filesystem paths."""

    _sync_runtime_dependencies()
    return _cmd_bind(
        domain,
        debug=debug,
        config_dir=CONFIG_DIR,
        public_key_path=PUBLIC_KEY_PATH,
        binds_path=BINDS_PATH,
        unsigned=unsigned,
        anonymous=anonymous,
        require_configured_keys=require_configured_keys,
        load_signing_key_pair=load_signing_key_pair,
    )


def cmd_echo(
    domain: str,
    debug: bool = False,
    unsigned: bool = False,
    anonymous: bool = False
) -> int:
    """Run the echo command with the current filesystem paths."""

    _sync_runtime_dependencies()
    return _cmd_echo(
        domain,
        debug=debug,
        config_dir=CONFIG_DIR,
        binds_path=BINDS_PATH,
        unsigned=unsigned,
        anonymous=anonymous,
        require_configured_keys=require_configured_keys,
        load_signing_key_pair=load_signing_key_pair,
    )


def cmd_shell(
    domain: str,
    debug: bool = False,
    unsigned: bool = False,
    anonymous: bool = False
) -> int:
    """Run the interactive shell command with the current filesystem paths."""

    _sync_runtime_dependencies()
    return _cmd_shell(
        domain,
        debug=debug,
        config_dir=CONFIG_DIR,
        binds_path=BINDS_PATH,
        history_dir=HISTORY_DIR,
        readline=readline,
        unsigned=unsigned,
        anonymous=anonymous,
        require_configured_keys=require_configured_keys,
        load_signing_key_pair=load_signing_key_pair,
    )


def cmd_msg(
    message: list[str],
    debug: bool = False,
    unsigned: bool = False,
    anonymous: bool = False
) -> int:
    """Run the flexible message command with the current filesystem paths."""

    _sync_runtime_dependencies()
    return _cmd_msg(
        message,
        debug = debug,
        config_dir = CONFIG_DIR,
        unsigned = unsigned,
        anonymous = anonymous,
        require_configured_keys = require_configured_keys,
        load_signing_key_pair = load_signing_key_pair,
    )


def cmd_test(
    path: str | None,
    debug: bool = False,
    unsigned: bool = False,
    anonymous: bool = False
) -> int:
    """Run the wrapped message test command with the current filesystem paths."""

    _sync_runtime_dependencies()
    return _cmd_test(
        path,
        debug = debug,
        config_dir = CONFIG_DIR,
        binds_path = BINDS_PATH,
        unsigned = unsigned,
        anonymous = anonymous,
        require_configured_keys = require_configured_keys,
        load_signing_key_pair = load_signing_key_pair,
    )


def cmd_chat(
    domain: str | None = None,
    debug: bool = False,
    test: bool = False,
    unsigned: bool = False,
    anonymous: bool = False
) -> int:
    """Run the chat command with the current filesystem paths."""

    _sync_runtime_dependencies()
    return _cmd_chat(
        domain = domain,
        debug = debug,
        test = test,
        unsigned = unsigned,
        anonymous = anonymous,
        config_path = CONFIG_PATH,
        require_configured_keys = require_configured_keys,
        load_signing_key_pair = load_signing_key_pair,
    )


def cmd_sync(
    domain: str,
    debug: bool = False,
    unsigned: bool = False,
    anonymous: bool = False
) -> int:
    """Run the sync command with the current filesystem paths."""

    _sync_runtime_dependencies()
    return _cmd_sync(
        domain,
        debug=debug,
        config_dir=CONFIG_DIR,
        binds_path=BINDS_PATH,
        sync_dir=SYNC_DIR,
        unsigned=unsigned,
        anonymous=anonymous,
        require_configured_keys=require_configured_keys,
        load_signing_key_pair=load_signing_key_pair,
    )


def main(argv: list[str] | None = None) -> int:
    """Dispatch CLI arguments to the appropriate feature command."""

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] != "upgrade":
        preflight_result = _maybe_upgrade_before_command(argv)
        if preflight_result is not None:
            return preflight_result

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "version":
            return cmd_version()
        if args.command == "upgrade":
            return cmd_upgrade()
        if args.command == "config":
            return cmd_config(
                force=args.force,
                debug=args.debug,
            )
        if args.command == "bind":
            return cmd_bind(
                domain = args.domain,
                debug = args.debug,
                unsigned = args.unsigned,
                anonymous = args.anonymous)
        if args.command == "echo":
            return cmd_echo(
                domain = args.domain,
                debug = args.debug,
                unsigned = args.unsigned,
                anonymous = args.anonymous)
        if args.command == "msg":
            return cmd_msg(
                message = args.message,
                debug = args.debug,
                unsigned = args.unsigned,
                anonymous = args.anonymous)
        if args.command == "test":
            return cmd_test(
                path = args.path,
                debug = args.debug,
                unsigned = args.unsigned,
                anonymous = args.anonymous)
        if args.command == "shell":
            return cmd_shell(
                domain = args.domain,
                debug = args.debug,
                unsigned = args.unsigned,
                anonymous = args.anonymous)
        if args.command == "chat":
            return cmd_chat(
                domain = args.domain,
                debug = args.debug,
                test = args.test,
                unsigned = args.unsigned,
                anonymous = args.anonymous)
        if args.command == "sync":
            return cmd_sync(
                domain = args.domain,
                debug = args.debug,
                unsigned = args.unsigned,
                anonymous = args.anonymous)
    except UserFacingError as exc:
        print_error(f"Error: {exc}")
        return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
