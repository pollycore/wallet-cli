from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import hashlib
from importlib.metadata import PackageNotFoundError, version as get_installed_version
import json
import re
import shlex
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from pollyweb import KeyPair, Msg
import pollyweb.msg as pollyweb_msg
from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text

try:
    import readline
except ImportError:  # pragma: no cover - platform-dependent fallback
    readline = None


CONFIG_DIR = Path.home() / ".pollyweb"
PRIVATE_KEY_PATH = CONFIG_DIR / "private.pem"
PUBLIC_KEY_PATH = CONFIG_DIR / "public.pem"
BINDS_PATH = CONFIG_DIR / "binds.yaml"
HISTORY_DIR = CONFIG_DIR / "history"
SYNC_DIR = CONFIG_DIR / "sync"
BIND_SUBJECT = "Bind@Vault"
ECHO_SUBJECT = "Echo@Domain"
SHELL_SUBJECT = "Shell@Domain"
SYNC_SUBJECT = "Map@Filer"
SHELL_HISTORY_LIMIT = 20
BIND_PATTERN = re.compile(
    r"Bind:[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}"
)
BIND_SCHEMA_KEY = "Schema"
NOTIFIER_DOMAIN = "any-notifier.pollyweb.org"
NOTIFIER_SUBJECT = "Onboard@Notifier"
NOTIFIER_LANGUAGE = "en-us"


class UserFacingError(Exception):
    """A concise error intended to be shown directly to CLI users."""


@dataclass(frozen=True)
class EchoResponse:
    From: str
    To: str
    Subject: str
    Correlation: str
    Schema: str
    Selector: str = ""
    Algorithm: str = ""


DEBUG_CONSOLE = Console()
SHELL_CONSOLE = Console()
DEBUG_WRAP_WIDTH = 64
DEBUG_LITERAL_KEYS = frozenset({"PublicKey", "Signature", "Hash"})
DEBUG_KEY_STYLE = "bold #0f62fe"
DEBUG_VALUE_STYLE = "#d0e2ff"
DEBUG_LITERAL_STYLE = "#08bdba"
DEBUG_PUNCTUATION_STYLE = "dim"
ERROR_STYLE = "\033[1;31m"
ERROR_STYLE_RESET = "\033[0m"
HTTP_CODE_STYLES = {
    1: "cyan",
    2: "green",
    3: "blue",
    4: "yellow",
    5: "bold red",
}


class _LiteralDebugString(str):
    """Marker type for YAML literal block rendering in debug output."""


class _DebugDumper(yaml.SafeDumper):
    """YAML dumper for debug output formatting."""


def _represent_literal_debug_string(
    dumper: yaml.SafeDumper, data: _LiteralDebugString
) -> yaml.nodes.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(data), style="|")


_DebugDumper.add_representer(_LiteralDebugString, _represent_literal_debug_string)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pw",
        description="PollyWeb command line wallet.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_get_cli_version()}",
        help="Show the installed CLI version and exit.",
    )
    subparsers = parser.add_subparsers(dest="command")

    config_parser = subparsers.add_parser(
        "config",
        help="Generate a PollyWeb key pair in ~/.pollyweb.",
    )
    config_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing key pair.",
    )

    bind_parser = subparsers.add_parser(
        "bind",
        help="Bind the configured wallet key to a domain.",
    )
    bind_parser.add_argument("domain", help="Domain that will receive the bind request.")
    bind_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print outbound and inbound bind payloads.",
    )

    echo_parser = subparsers.add_parser(
        "echo",
        help="Send an echo request to a domain and verify the signed response.",
    )
    echo_parser.add_argument(
        "domain", help="Domain that will receive the echo request."
    )
    echo_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print outbound and inbound echo payloads.",
    )

    shell_parser = subparsers.add_parser(
        "shell",
        help="Open an interactive shell against a domain.",
    )
    shell_parser.add_argument(
        "domain", help="Domain that will receive shell commands."
    )
    shell_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print outbound and inbound shell payloads.",
    )

    sync_parser = subparsers.add_parser(
        "sync",
        help="Sync files from ~/.pollyweb/sync/{domain} to a domain.",
    )
    sync_parser.add_argument(
        "domain", help="Domain that will receive the sync request."
    )
    sync_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print outbound and inbound sync payloads.",
    )

    return parser


def print_error(message: str) -> None:
    if sys.stderr.isatty():
        print(f"{ERROR_STYLE}{message}{ERROR_STYLE_RESET}", file=sys.stderr)
        return
    print(message, file=sys.stderr)


def _get_cli_version() -> str:
    try:
        return get_installed_version("pollyweb-cli")
    except PackageNotFoundError:
        return "0+unknown"

def require_configured_keys() -> None:
    if PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists():
        return
    raise FileNotFoundError(
        f"Missing PollyWeb keys in {CONFIG_DIR}. Run `pw config` first."
    )


def load_signing_key_pair() -> KeyPair:
    private_key = load_pem_private_key(PRIVATE_KEY_PATH.read_bytes(), password=None)
    return KeyPair(PrivateKey=private_key)


def _parse_debug_payload(payload: str) -> object:
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {"Body": payload}


def _extract_http_code(payload: str) -> int | None:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None

    code_value = parsed.get("Code")
    if isinstance(code_value, int):
        return code_value
    if isinstance(code_value, str) and code_value.isdigit():
        return int(code_value)
    return None


def _get_http_code_style(code: int) -> str | None:
    return HTTP_CODE_STYLES.get(code // 100)


def _parse_shell_response_body(payload: str) -> tuple[str | None, str | None]:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None, None

    if not isinstance(parsed, dict):
        return None, None

    rendered_text = parsed.get("Body")
    if not isinstance(rendered_text, str):
        rendered_text = parsed.get("Message")
    if not isinstance(rendered_text, str):
        return None, None

    code = parsed.get("Code")
    if isinstance(code, int):
        return rendered_text, _get_http_code_style(code)
    if isinstance(code, str) and code.isdigit():
        return rendered_text, _get_http_code_style(int(code))
    return rendered_text, None


def print_shell_response(payload: str) -> None:
    body, body_style = _parse_shell_response_body(payload)
    if body is not None:
        SHELL_CONSOLE.print(Markdown(body), style=body_style)
        return

    code = _extract_http_code(payload)
    style = _get_http_code_style(code) if code is not None else None
    if style is None:
        print(payload)
        return
    SHELL_CONSOLE.print(payload, style=style)


def print_echo_response(payload: str) -> None:
    print_debug_payload("Echo response", _parse_debug_payload(payload))


def _format_debug_value(value: object, key: str | None = None) -> object:
    if isinstance(value, dict):
        return {
            child_key: _format_debug_value(item, key=child_key)
            for child_key, item in value.items()
        }
    if isinstance(value, list):
        return [_format_debug_value(item, key=key) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str) and type(value) is not str:
        value = str(value)
    elif not isinstance(value, str):
        value = str(value)
    if (
        isinstance(value, str)
        and not any(character.isspace() for character in value)
        and (
            key in DEBUG_LITERAL_KEYS or len(value) > DEBUG_WRAP_WIDTH
        )
    ):
        return _LiteralDebugString("\n".join(textwrap.wrap(value, DEBUG_WRAP_WIDTH)))
    return value


def print_debug_payload(title: str, payload: object) -> None:
    yaml_payload = yaml.dump(
        _format_debug_value(payload),
        sort_keys=False,
        allow_unicode=False,
        default_flow_style=False,
        Dumper=_DebugDumper,
    ).rstrip()
    print()
    print(f"{title}:")
    DEBUG_CONSOLE.print(_render_debug_yaml(yaml_payload), overflow="fold")
    print()


def _render_debug_yaml(yaml_payload: str) -> Text:
    rendered = Text()
    literal_indent: int | None = None

    for line in yaml_payload.splitlines():
        if rendered:
            rendered.append("\n")

        if not line:
            continue

        indent_width = len(line) - len(line.lstrip(" "))
        stripped = line[indent_width:]
        indent = line[:indent_width]

        if literal_indent is not None and (
            indent_width > literal_indent or not stripped
        ):
            rendered.append(indent, style=DEBUG_PUNCTUATION_STYLE)
            rendered.append(stripped, style=DEBUG_LITERAL_STYLE)
            continue
        literal_indent = None

        match = re.match(r"([^:]+):(.*)", stripped)
        if match is None:
            rendered.append(indent, style=DEBUG_PUNCTUATION_STYLE)
            rendered.append(stripped, style=DEBUG_LITERAL_STYLE)
            continue

        key, remainder = match.groups()
        rendered.append(indent, style=DEBUG_PUNCTUATION_STYLE)
        rendered.append(key, style=DEBUG_KEY_STYLE)
        rendered.append(":", style=DEBUG_PUNCTUATION_STYLE)
        if remainder:
            rendered.append(remainder, style=DEBUG_VALUE_STYLE)
        if remainder.strip() == "|":
            literal_indent = indent_width

    return rendered


def serialize_public_key_value(public_key_pem: str) -> str:
    lines = [line.strip() for line in public_key_pem.splitlines() if line.strip()]
    return "".join(line for line in lines if not line.startswith("-----"))


def _parse_bind_response(payload: str) -> dict[str, str]:
    match = BIND_PATTERN.search(payload)
    bind_value = match.group(0) if match is not None else None
    schema_value: str | None = None

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, dict):
        bind_candidate = parsed.get("Bind")
        if isinstance(bind_candidate, str) and BIND_PATTERN.fullmatch(bind_candidate):
            bind_value = bind_candidate

        schema_candidate = parsed.get(BIND_SCHEMA_KEY)
        if isinstance(schema_candidate, str):
            schema_value = schema_candidate

        body = parsed.get("Body")
        if isinstance(body, dict):
            bind_candidate = body.get("Bind")
            if isinstance(bind_candidate, str) and BIND_PATTERN.fullmatch(bind_candidate):
                bind_value = bind_candidate
            schema_candidate = body.get(BIND_SCHEMA_KEY)
            if isinstance(schema_candidate, str):
                schema_value = schema_candidate

    if bind_value is None:
        preview = " ".join(payload.split())
        if len(preview) > 160:
            preview = preview[:157] + "..."
        raise UserFacingError(
            "\n".join(
                [
                    f"Could not bind {{domain}}.",
                    "The server replied, but it did not include a bind token.",
                    "Expected a value like `Bind:<UUID>` in the response body.",
                    (
                        f"Response preview: {preview}"
                        if preview
                        else "Response preview: <empty response>"
                    ),
                    "This usually means the host is not returning the expected PollyWeb bind response yet.",
                ]
            )
        )

    entry = {"Bind": bind_value}
    if schema_value is not None:
        entry[BIND_SCHEMA_KEY] = schema_value
    return entry


def send_bind_message(domain: str, key_pair: KeyPair, debug: bool = False) -> dict[str, str]:
    public_key = serialize_public_key_value(
        PUBLIC_KEY_PATH.read_text(encoding="utf-8")
    )
    payload = post_signed_message(
        domain=domain,
        subject=BIND_SUBJECT,
        body={"PublicKey": public_key},
        key_pair=key_pair,
        debug=debug,
        schema_value=None,
    )

    try:
        return _parse_bind_response(payload)
    except UserFacingError as exc:
        raise UserFacingError(str(exc).replace("{domain}", domain)) from None


def build_signed_message(
    subject: str,
    body: dict[str, object],
    key_pair: KeyPair,
    domain: str,
    from_value: str | None = "Anonymous",
    schema_value: str | None = "pollyweb.org/MSG:1.0",
) -> dict[str, object]:
    message_kwargs: dict[str, str | dict[str, object]] = {
        "To": domain,
        "Subject": subject,
        "Body": body,
    }
    if from_value is not None:
        message_kwargs["From"] = from_value
    if schema_value is not None:
        message_kwargs["Schema"] = schema_value

    if from_value is None or schema_value is None:
        template_message = Msg(**message_kwargs)
        header = {
            "To": template_message.To,
            "Subject": template_message.Subject,
            "Correlation": template_message.Correlation,
            "Timestamp": template_message.Timestamp,
        }
        if from_value is not None:
            header["From"] = template_message.From
        if schema_value is not None:
            header["Schema"] = template_message.Schema

        signed_payload = {
            "Header": header,
            "Body": template_message.Body,
        }
        canonical = json.dumps(
            signed_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        request_message = {
            **signed_payload,
            "Hash": hashlib.sha256(canonical).hexdigest(),
            "Signature": base64.b64encode(
                key_pair.PrivateKey.sign(canonical)
            ).decode("ascii"),
        }
    else:
        message = Msg(**message_kwargs).sign(key_pair.PrivateKey)
        request_message = message.to_dict()
    return request_message


def send_request_message(
    domain: str,
    request_message: dict[str, object],
    debug: bool = False,
) -> str:
    request_payload = json.dumps(request_message, separators=(",", ":"))
    request_url = f"https://pw.{domain}/inbox"

    if debug:
        print_debug_payload(f"Outbound payload to {request_url}", request_message)

    request = urllib.request.Request(
        request_url,
        data=request_payload.encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        response_payload = response.read().decode("utf-8")

    if debug:
        print_debug_payload("Inbound payload", _parse_debug_payload(response_payload))

    return response_payload


def post_signed_message(
    domain: str,
    subject: str,
    body: dict[str, object],
    key_pair: KeyPair,
    debug: bool = False,
    from_value: str | None = "Anonymous",
    schema_value: str | None = "pollyweb.org/MSG:1.0",
) -> str:
    request_message = build_signed_message(
        subject=subject,
        body=body,
        key_pair=key_pair,
        domain=domain,
        from_value=from_value,
        schema_value=schema_value,
    )
    return send_request_message(domain=domain, request_message=request_message, debug=debug)


def parse_and_verify_echo_response(
    payload: str,
    *,
    domain: str,
    request_correlation: str,
    expected_to: str,
) -> tuple[EchoResponse, object | None]:
    try:
        response = Msg.parse(payload)
    except Exception as parse_exc:
        try:
            loaded = json.loads(payload)
            header = loaded["Header"]
            body = loaded.get("Body", {})
            signature_b64 = loaded["Signature"]
            payload_hash = loaded["Hash"]
            canonical_payload = {"Body": body, "Header": header}
            canonical = json.dumps(
                canonical_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        except Exception:
            raise UserFacingError(
                f"Could not parse the echo response from {domain}: {parse_exc}"
            ) from None
        try:
            if payload_hash != hashlib.sha256(canonical).hexdigest():
                raise UserFacingError(
                    f"Echo response from {domain} did not verify: Hash mismatch"
                ) from None

            public_key, key_type = pollyweb_msg._resolve_dkim_public_key(
                header["From"], header["Selector"]
            )
            signature_algorithm = header.get("Algorithm") or None
            if public_key is not None and signature_algorithm is None:
                signature_algorithm = pollyweb_msg.signature_algorithm_for_public_key(
                    public_key
                )
            pollyweb_msg.verify_signature(
                public_key,
                base64.b64decode(signature_b64),
                canonical,
                signature_algorithm=signature_algorithm,
                key_type=key_type,
            )
        except UserFacingError:
            raise
        except Exception as exc:
            details = str(exc) or (
                "Invalid signature"
                if exc.__class__.__name__ == "InvalidSignature"
                else exc.__class__.__name__
            )
            raise UserFacingError(
                f"Echo response from {domain} did not verify: {details}"
            ) from None
        parsed_response = EchoResponse(
            From=header["From"],
            To=header["To"],
            Subject=header["Subject"],
            Correlation=header["Correlation"],
            Schema=str(header["Schema"]),
            Selector=header.get("Selector", ""),
            Algorithm=header.get("Algorithm", ""),
        )
        verification = pollyweb_msg.VerificationDetails(
            schema=str(header["Schema"]),
            required_headers_present=True,
            hash_valid=True,
            signature_valid=True,
            dns_lookup_used=True,
            from_value=header["From"],
            to_value=header["To"],
            subject=header["Subject"],
            correlation=header["Correlation"],
            selector=header.get("Selector", ""),
            algorithm=signature_algorithm or "",
        )
    else:
        parsed_response = EchoResponse(
            From=response.From,
            To=response.To,
            Subject=response.Subject,
            Correlation=response.Correlation,
            Schema=str(response.Schema),
            Selector=response.Selector,
            Algorithm=response.Algorithm,
        )
        try:
            verification = (
                response.verify_details() if hasattr(response, "verify_details") else None
            )
            if verification is None:
                response.verify()
        except Exception as exc:
            raise UserFacingError(
                f"Echo response from {domain} did not verify: {exc}"
            ) from None

    if parsed_response.From != domain:
        raise UserFacingError(
            f"Echo response from {domain} had an unexpected From value: {parsed_response.From}"
        ) from None
    if parsed_response.Subject != ECHO_SUBJECT:
        raise UserFacingError(
            f"Echo response from {domain} had an unexpected Subject: {parsed_response.Subject}"
        ) from None
    if parsed_response.Correlation != request_correlation:
        raise UserFacingError(
            f"Echo response from {domain} had an unexpected Correlation: {parsed_response.Correlation}"
        ) from None
    if parsed_response.To != expected_to:
        raise UserFacingError(
            f"Echo response from {domain} had an unexpected To value: {parsed_response.To}"
        ) from None

    return parsed_response, verification


def load_binds() -> list[dict[str, str]]:
    if not BINDS_PATH.exists():
        return []

    loaded = yaml.safe_load(BINDS_PATH.read_text(encoding="utf-8"))
    if loaded is None:
        return []
    if not isinstance(loaded, list):
        raise ValueError(f"{BINDS_PATH} must contain a YAML array.")
    binds: list[dict[str, str]] = []
    for item in loaded:
        if not isinstance(item, dict):
            raise ValueError(f"{BINDS_PATH} entries must be YAML objects.")
        bind = item.get("Bind")
        domain = item.get("Domain")
        if not isinstance(bind, str) or not isinstance(domain, str):
            raise ValueError(f"{BINDS_PATH} entries must contain string Bind and Domain.")
        entry = {"Bind": bind, "Domain": domain}
        schema = item.get(BIND_SCHEMA_KEY)
        if schema is not None:
            if not isinstance(schema, str):
                raise ValueError(
                    f"{BINDS_PATH} Schema values must be strings when present."
                )
            entry[BIND_SCHEMA_KEY] = schema
        binds.append(entry)
    return binds


def save_bind(bind_entry: dict[str, str], domain: str) -> None:
    binds = load_binds()
    entry = {**bind_entry, "Domain": domain}
    schema = entry.get(BIND_SCHEMA_KEY)
    binds = [
        existing
        for existing in binds
        if not (
            existing["Domain"] == domain
            and existing.get(BIND_SCHEMA_KEY) == schema
        )
    ]
    binds.append(entry)
    BINDS_PATH.write_text(yaml.safe_dump(binds, sort_keys=False), encoding="utf-8")
    BINDS_PATH.chmod(0o600)


def get_first_bind_for_domain(domain: str, binds: list[dict[str, str]]) -> str | None:
    for bind in binds:
        if bind["Domain"] == domain:
            return bind["Bind"]
    return None


def get_shell_from_value(bind_value: str) -> str:
    if bind_value.startswith("Bind:"):
        return bind_value.split(":", 1)[1]
    return bind_value


def parse_shell_command(command_line: str) -> tuple[str, list[str]]:
    try:
        parts = shlex.split(command_line)
    except ValueError as exc:
        raise UserFacingError(f"Invalid shell command: {exc}") from None

    if not parts:
        raise UserFacingError("Shell command cannot be empty.")

    return parts[0], parts[1:]


def is_shell_exit_command(command: str) -> bool:
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


def get_shell_history_path(domain: str) -> Path:
    encoded_domain = urllib.parse.quote(domain, safe="")
    return HISTORY_DIR / f"{encoded_domain}.txt"


def load_shell_history(domain: str) -> list[str]:
    history_path = get_shell_history_path(domain)
    if not history_path.exists():
        return []
    return [
        line
        for line in history_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ][-SHELL_HISTORY_LIMIT:]


def save_shell_history(domain: str, commands: list[str]) -> None:
    HISTORY_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    history_path = get_shell_history_path(domain)
    trimmed_commands = commands[-SHELL_HISTORY_LIMIT:]
    trailing_newline = "\n" if trimmed_commands else ""
    history_path.write_text(
        "\n".join(trimmed_commands) + trailing_newline,
        encoding="utf-8",
    )
    history_path.chmod(0o600)


def configure_shell_history(domain: str) -> list[str]:
    history = load_shell_history(domain)
    if readline is None:
        return history

    readline.clear_history()
    for command in history:
        readline.add_history(command)
    readline.set_history_length(SHELL_HISTORY_LIMIT)
    return history


def record_shell_history(domain: str, history: list[str], command: str) -> list[str]:
    updated_history = [*history, command][-SHELL_HISTORY_LIMIT:]
    save_shell_history(domain, updated_history)
    if readline is not None:
        readline.add_history(command)
    return updated_history


def send_onboard_message(public_key: bytes) -> dict[str, object]:
    """Send an Onboard@Notifier message to register the new wallet public key.

    Args:
        public_key: The PEM-encoded public key bytes to register.

    Returns:
        The parsed JSON response dict from the notifier, or an empty dict.
    """
    # Build the unsigned onboard message with the public key in the body
    message = {
        "Header": {
            "From": "Anonymous",
            "To": NOTIFIER_DOMAIN,
            "Subject": NOTIFIER_SUBJECT,
        },
        "Body": {
            "Language": NOTIFIER_LANGUAGE,
            "PublicKey": public_key.decode("ascii"),
        },
    }

    # POST the message to the notifier inbox
    request = urllib.request.Request(
        f"https://pw.{NOTIFIER_DOMAIN}/inbox",
        data=json.dumps(message, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request) as response:
        payload = response.read()

    if not payload:
        return {}

    result = json.loads(payload)
    if not isinstance(result, dict):
        raise ValueError("Notifier onboard response must be a JSON object.")
    return result


def cmd_config(force: bool) -> int:
    private_exists = PRIVATE_KEY_PATH.exists()
    public_exists = PUBLIC_KEY_PATH.exists()

    if not force and private_exists and public_exists:
        print(f"Using existing {PRIVATE_KEY_PATH}")
        print(f"Using existing {PUBLIC_KEY_PATH}")
        return 0

    if not force and (private_exists or public_exists):
        print(
            "Key files are only partially configured. Re-run with --force to recreate them.",
            file=sys.stderr,
        )
        return 1

    CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

    key_pair = KeyPair()
    private_pem = key_pair.private_pem_bytes()
    public_pem = key_pair.public_pem_bytes()
    PRIVATE_KEY_PATH.write_bytes(private_pem)
    PUBLIC_KEY_PATH.write_bytes(public_pem)
    PRIVATE_KEY_PATH.chmod(0o600)
    PUBLIC_KEY_PATH.chmod(0o644)

    print(f"Created {PRIVATE_KEY_PATH}")
    print(f"Created {PUBLIC_KEY_PATH}")

    # Notify the onboard service about the new wallet public key
    try:
        onboard_response = send_onboard_message(public_pem)
        if wallet := onboard_response.get("Wallet"):
            print(f"Wallet: {wallet}")
    except Exception:
        # Onboard notification is best-effort; don't fail config if it's unreachable
        pass

    return 0


def cmd_bind(domain: str, debug: bool = False) -> int:
    try:
        require_configured_keys()
        key_pair = load_signing_key_pair()
        bind_entry = send_bind_message(domain, key_pair, debug=debug)
        save_bind(bind_entry, domain)
    except FileNotFoundError:
        raise UserFacingError(
            f"Missing PollyWeb keys in {CONFIG_DIR}. Run `pw config` first."
        ) from None
    except urllib.error.HTTPError as exc:
        raise UserFacingError(
            f"Could not bind {domain}. The server returned HTTP {exc.code}."
        ) from None
    except urllib.error.URLError as exc:
        reason = exc.reason if isinstance(exc.reason, str) else repr(exc.reason)
        raise UserFacingError(
            f"Could not bind {domain}. Network request failed: {reason}"
        ) from None

    print(f"Stored bind for {domain}: {bind_entry['Bind']}")
    print(f"Updated {BINDS_PATH}")
    return 0


def cmd_echo(domain: str, debug: bool = False) -> int:
    try:
        require_configured_keys()
        key_pair = load_signing_key_pair()
        request_message = build_signed_message(
            subject=ECHO_SUBJECT,
            body={},
            key_pair=key_pair,
            domain=domain,
        )
        response_payload = send_request_message(
            domain=domain, request_message=request_message, debug=debug
        )
        response, verification = parse_and_verify_echo_response(
            response_payload,
            domain=domain,
            request_correlation=str(request_message["Header"]["Correlation"]),
            expected_to=str(request_message["Header"].get("From", "Anonymous")),
        )
    except FileNotFoundError:
        raise UserFacingError(
            f"Missing PollyWeb keys in {CONFIG_DIR}. Run `pw config` first."
        ) from None
    except urllib.error.HTTPError as exc:
        raise UserFacingError(
            f"Echo request to {domain} failed with HTTP {exc.code}."
        ) from None
    except urllib.error.URLError as exc:
        reason = exc.reason if isinstance(exc.reason, str) else repr(exc.reason)
        raise UserFacingError(
            f"Echo request to {domain} failed: {reason}"
        ) from None

    print_echo_response(response_payload)
    if not debug:
        print("Verified echo response: ✅")
        return 0

    print(f"Verified echo response from {domain}:")
    if verification is not None:
        print(f" - Schema validated: {verification.schema}")
        print(" - Required signed headers were present")
        print(" - Canonical payload hash matched the signed content")
        if verification.dns_lookup_used:
            print(
                f" - Signature verified via DKIM lookup for selector "
                f"{verification.selector} on {verification.from_value}"
            )
        else:
            print(" - Signature verified with the provided public key")
    else:
        print(f" - Schema validated: {response.Schema}")
        print(" - Required signed headers were present")
        print(" - Canonical payload hash matched the signed content")
        print(
            f" - Signature verified via DKIM lookup for selector {response.Selector} "
            f"on {response.From}"
        )
    print(f" - From matched expected domain: {response.From}")
    print(f" - To matched expected sender: {response.To}")
    print(f" - Subject matched expected echo subject: {response.Subject}")
    print(f" - Correlation matched the request: {response.Correlation}")
    return 0


def cmd_shell(domain: str, debug: bool = False) -> int:
    try:
        require_configured_keys()
        key_pair = load_signing_key_pair()
        binds = load_binds()
    except FileNotFoundError:
        raise UserFacingError(
            f"Missing PollyWeb keys in {CONFIG_DIR}. Run `pw config` first."
        ) from None
    except ValueError as exc:
        raise UserFacingError(str(exc)) from None

    bind_value = get_first_bind_for_domain(domain, binds)
    if bind_value is None:
        raise UserFacingError(
            f"No bind stored for {domain}. Run `pw bind {domain}` first."
        ) from None
    from_value = get_shell_from_value(bind_value)


    history = configure_shell_history(domain)

    available_commands = []

    def send_shell_command(command_name: str, command_args: list[str], capture_response: bool = False):
        try:
            response = post_signed_message(
                domain=domain,
                subject=SHELL_SUBJECT,
                body={
                    "Command": command_name,
                    "Arguments": build_shell_arguments(command_args),
                },
                key_pair=key_pair,
                debug=debug,
                from_value=from_value,
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

    # Send help silently to extract available commands for autocomplete
    try:
        help_response = send_shell_command("help", [], capture_response=True)
        help_json = json.loads(help_response)
        shell_data = help_json.get("Shell")
        if isinstance(shell_data, dict):
            commands_list = shell_data.get("commands", [])
            if isinstance(commands_list, list):
                available_commands = [
                    cmd["name"] for cmd in commands_list 
                    if isinstance(cmd, dict) and "name" in cmd
                ]
    except Exception:
        available_commands = []

    # Setup readline completer if available
    if readline is not None and available_commands:
        def completer(text, state):
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
        history = record_shell_history(domain, history, command)
        send_shell_command(command_name, command_args)


def build_sync_files_map(domain: str) -> dict[str, dict[str, str]]:
    sync_domain_dir = SYNC_DIR / domain
    if not sync_domain_dir.exists():
        raise UserFacingError(
            f"Sync directory {sync_domain_dir} does not exist."
        )
    files: dict[str, dict[str, str]] = {}
    for file_path in sorted(sync_domain_dir.rglob("*")):
        if file_path.is_file():
            relative = "/" + file_path.relative_to(sync_domain_dir).as_posix()
            sha1 = hashlib.sha1(file_path.read_bytes()).hexdigest()
            files[relative] = {"Hash": sha1}
    return files


def cmd_sync(domain: str, debug: bool = False) -> int:
    try:
        require_configured_keys()
        key_pair = load_signing_key_pair()
        binds = load_binds()
    except FileNotFoundError:
        raise UserFacingError(
            f"Missing PollyWeb keys in {CONFIG_DIR}. Run `pw config` first."
        ) from None
    except ValueError as exc:
        raise UserFacingError(str(exc)) from None

    bind_value = get_first_bind_for_domain(domain, binds)
    if bind_value is None:
        raise UserFacingError(
            f"No bind stored for {domain}. Run `pw bind {domain}` first."
        ) from None
    from_value = get_shell_from_value(bind_value)

    files = build_sync_files_map(domain)

    try:
        response_payload = post_signed_message(
            domain=domain,
            subject=SYNC_SUBJECT,
            body={"Files": files},
            key_pair=key_pair,
            debug=debug,
            from_value=from_value,
        )
    except urllib.error.HTTPError as exc:
        raise UserFacingError(
            f"Sync request to {domain} failed with HTTP {exc.code}."
        ) from None
    except urllib.error.URLError as exc:
        reason = exc.reason if isinstance(exc.reason, str) else repr(exc.reason)
        raise UserFacingError(
            f"Sync request to {domain} failed: {reason}"
        ) from None

    try:
        response = json.loads(response_payload)
    except json.JSONDecodeError:
        raise UserFacingError(
            f"Could not parse sync response from {domain}."
        ) from None

    map_id = response.get("Map")
    response_files = response.get("Files", {})

    if map_id:
        print(f"Map: {map_id}")
    for file_path, file_info in response_files.items():
        action = file_info.get("Action", "")
        print(f"{action}: {file_path}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "config":
            return cmd_config(force=args.force)
        if args.command == "bind":
            return cmd_bind(domain=args.domain, debug=args.debug)
        if args.command == "echo":
            return cmd_echo(domain=args.domain, debug=args.debug)
        if args.command == "shell":
            return cmd_shell(domain=args.domain, debug=args.debug)
        if args.command == "sync":
            return cmd_sync(domain=args.domain, debug=args.debug)
    except UserFacingError as exc:
        print_error(f"Error: {exc}")
        return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
