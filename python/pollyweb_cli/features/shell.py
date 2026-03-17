"""Interactive shell feature helpers and command implementation."""

from __future__ import annotations

import json
import shlex
import urllib.error
import urllib.parse
from pathlib import Path

from pollyweb_cli.features.bind import get_first_bind_for_domain, load_binds
from pollyweb_cli.tools.debug import print_shell_response
from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.tools.transport import send_wallet_message


SHELL_SUBJECT = "Shell@Domain"
SHELL_HISTORY_LIMIT = 20


def get_shell_from_value(bind_value: str) -> str:
    """Translate a bind token into the sender value used for shell requests."""

    if bind_value.startswith("Bind:"):
        return bind_value.split(":", 1)[1]
    return bind_value


def parse_shell_command(command_line: str) -> tuple[str, list[str]]:
    """Parse a shell command line into a command name and argument list."""

    try:
        parts = shlex.split(command_line)
    except ValueError as exc:
        raise UserFacingError(f"Invalid shell command: {exc}") from None

    if not parts:
        raise UserFacingError("Shell command cannot be empty.")

    return parts[0], parts[1:]


def is_shell_exit_command(command: str) -> bool:
    """Recognize common shell exit commands used by interactive users."""

    normalized = command.strip().lower()
    if normalized in {"exit", "quit"}:
        return True

    if normalized.startswith(("!", ":")):
        normalized = normalized[1:]
        if normalized.endswith("!"):
            normalized = normalized[:-1]
        if normalized in {"q", "quit", "qa", "qall", "wq", "x"}:
            return True

    return False


def build_shell_arguments(command_args: list[str]) -> dict[str, str]:
    """Convert shell arguments into the command argument map expected by the API."""

    arguments: dict[str, str] = {}
    positional_index = 0
    index = 0

    while index < len(command_args):
        argument = command_args[index]

        if argument.startswith("--") and len(argument) > 2:
            key = argument[2:]
            next_index = index + 1
            if next_index < len(command_args):
                arguments[key] = command_args[next_index]
                index += 2
                continue

        if argument.startswith("-") and len(argument) == 2:
            key = argument[1:]
            next_index = index + 1
            if next_index < len(command_args):
                arguments[key] = command_args[next_index]
                index += 2
                continue

        if "=" in argument:
            key, value = argument.split("=", 1)
            if key:
                arguments[key] = value
                index += 1
                continue

        arguments[str(positional_index)] = argument
        positional_index += 1
        index += 1

    return arguments


def get_shell_history_path(domain: str, history_dir: Path) -> Path:
    """Return the per-domain readline history file path."""

    encoded_domain = urllib.parse.quote(domain, safe="")
    return history_dir / f"{encoded_domain}.txt"


def load_shell_history(domain: str, history_dir: Path) -> list[str]:
    """Load the recent shell history for a domain."""

    history_path = get_shell_history_path(domain, history_dir)
    if not history_path.exists():
        return []
    return [
        line
        for line in history_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ][-SHELL_HISTORY_LIMIT:]


def save_shell_history(
    domain: str,
    commands: list[str],
    history_dir: Path
) -> None:
    """Persist the bounded shell history for a domain."""

    history_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    history_path = get_shell_history_path(domain, history_dir)
    trimmed_commands = commands[-SHELL_HISTORY_LIMIT:]
    trailing_newline = "\n" if trimmed_commands else ""
    history_path.write_text(
        "\n".join(trimmed_commands) + trailing_newline,
        encoding="utf-8",
    )
    history_path.chmod(0o600)


def configure_shell_history(domain: str, history_dir: Path, readline) -> list[str]:
    """Load shell history and attach it to readline when available."""

    history = load_shell_history(domain, history_dir)
    if readline is None:
        return history

    readline.clear_history()
    for command in history:
        readline.add_history(command)
    readline.set_history_length(SHELL_HISTORY_LIMIT)
    return history


def record_shell_history(
    domain: str,
    history: list[str],
    command: str,
    history_dir: Path,
    readline
) -> list[str]:
    """Append a command to history storage and readline state."""

    updated_history = [*history, command][-SHELL_HISTORY_LIMIT:]
    save_shell_history(domain, updated_history, history_dir)
    if readline is not None:
        readline.add_history(command)
    return updated_history


def cmd_shell(
    domain: str,
    *,
    debug: bool,
    config_dir: Path,
    binds_path: Path,
    history_dir: Path,
    readline,
    unsigned: bool,
    anonymous: bool,
    require_configured_keys,
    load_signing_key_pair
) -> int:
    """Run the interactive shell against the bound domain."""

    try:
        require_configured_keys()
        key_pair = load_signing_key_pair()
        binds = load_binds(binds_path)
    except FileNotFoundError:
        raise UserFacingError(
            f"Missing PollyWeb keys in {config_dir}. Run `pw config` first."
        ) from None
    except ValueError as exc:
        raise UserFacingError(str(exc)) from None

    bind_value = get_first_bind_for_domain(domain, binds)
    if bind_value is None and not anonymous:
        raise UserFacingError(
            f"No bind stored for {domain}. Run `pw bind {domain}` first."
        ) from None
    from_value = "Anonymous" if anonymous else get_shell_from_value(bind_value)
    history = configure_shell_history(domain, history_dir, readline)
    available_commands: list[str] = []

    def send_shell_command(
        command_name: str,
        command_args: list[str],
        capture_response: bool = False
    ):
        """Send a shell command and optionally return the raw response payload."""

        try:
            response, _, _ = send_wallet_message(
                domain=domain,
                subject=SHELL_SUBJECT,
                body={
                    "Command": command_name,
                    "Arguments": build_shell_arguments(command_args),
                },
                key_pair=key_pair,
                debug=debug,
                from_value=from_value,
                anonymous=anonymous,
                unsigned=unsigned,
            )
        except urllib.error.HTTPError as exc:
            raise UserFacingError(
                f"Shell request to {domain} failed with HTTP {exc.code}."
            ) from None
        except urllib.error.URLError as exc:
            reason = exc.reason if isinstance(exc.reason, str) else repr(exc.reason)
            raise UserFacingError(
                f"Shell request to {domain} failed: {reason}"
            ) from None

        if capture_response:
            return response
        print_shell_response(response)
        return None

    # Ask the remote shell for its command list before enabling completion.
    try:
        help_response = send_shell_command("help", [], capture_response=True)
        help_json = json.loads(help_response)
        shell_data = help_json.get("Shell")
        if isinstance(shell_data, dict):
            commands_list = shell_data.get("commands", [])
            if isinstance(commands_list, list):
                available_commands = [
                    cmd["name"]
                    for cmd in commands_list
                    if isinstance(cmd, dict) and "name" in cmd
                ]
    except Exception:
        available_commands = []

    if readline is not None and available_commands:
        def completer(text, state):
            """Provide basic prefix completion for remote shell commands."""

            matches = [cmd for cmd in available_commands if cmd.startswith(text)]
            if state < len(matches):
                return matches[state]
            return None

        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")

    while True:
        try:
            command = input(f"pw:{domain}> ")
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            return 0

        if not command.strip():
            continue

        if is_shell_exit_command(command):
            return 0

        command_name, command_args = parse_shell_command(command)
        history = record_shell_history(
            domain,
            history,
            command,
            history_dir,
            readline,
        )
        send_shell_command(command_name, command_args)
