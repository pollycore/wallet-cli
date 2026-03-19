"""Bind feature helpers and command implementation."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as get_installed_version
import json
import os
import re
import socket
import subprocess
import sys
from datetime import datetime
import urllib.error
from pathlib import Path

import yaml
from pollyweb import KeyPair, normalize_domain_name

from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.tools.debug import parse_debug_payload, print_yaml_payload
from pollyweb_cli.tools.transport import send_wallet_message


BIND_SUBJECT = "Bind@Vault"
BIND_SCHEMA_KEY = "Schema"
UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}"
)
BIND_PATTERN = re.compile(
    rf"Bind:{UUID_PATTERN.pattern}"
)
MACOS_NOTIFICATION_TITLE = "PollyWeb bind changed"
CLI_PACKAGE_NAME = "pollyweb-cli"
PYTEST_CURRENT_TEST_ENV = "PYTEST_CURRENT_TEST"


def normalize_bind_value(bind_value: str) -> str:
    """Convert a bind token into the UUID-only value stored locally."""

    if bind_value.startswith("Bind:"):
        return bind_value.split(":", 1)[1]
    return bind_value


def parse_bind_candidate(bind_candidate: object) -> str | None:
    """Normalize a supported bind reply value into the stored UUID."""

    if not isinstance(bind_candidate, str):
        return None

    if BIND_PATTERN.fullmatch(bind_candidate):
        return normalize_bind_value(bind_candidate)

    if UUID_PATTERN.fullmatch(bind_candidate):
        return bind_candidate

    return None


def normalize_bind_domain(domain: str) -> str:
    """Normalize supported bind-domain aliases to canonical hostnames."""

    return normalize_domain_name(domain)


def serialize_public_key_value(public_key_pem: str) -> str:
    """Strip PEM framing so the public key can be sent in message bodies."""

    lines = [line.strip() for line in public_key_pem.splitlines() if line.strip()]
    return "".join(line for line in lines if not line.startswith("-----"))


def parse_bind_response(payload: str) -> dict[str, str]:
    """Extract the bind token and optional schema from a bind response."""

    bind_value = parse_bind_candidate(payload.strip())

    if bind_value is None:
        match = BIND_PATTERN.search(payload)
        bind_value = normalize_bind_value(match.group(0)) if match is not None else None

    schema_value: str | None = None

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, dict):
        bind_candidate = parse_bind_candidate(parsed.get("Bind"))
        if bind_candidate is not None:
            bind_value = bind_candidate

        schema_candidate = parsed.get(BIND_SCHEMA_KEY)
        if isinstance(schema_candidate, str):
            schema_value = schema_candidate

        body = parsed.get("Body")
        if isinstance(body, dict):
            bind_candidate = parse_bind_candidate(body.get("Bind"))
            if bind_candidate is not None:
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
                    "Could not bind {domain}.",
                    "The server replied, but it did not include a bind token.",
                    "Expected a bare UUID bind value in the response body.",
                    "The legacy `Bind:<UUID>` format is still accepted for compatibility.",
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


def load_binds(binds_path: Path) -> list[dict[str, str]]:
    """Load persisted binds from disk and validate their structure."""

    if not binds_path.exists():
        return []

    loaded = yaml.safe_load(binds_path.read_text(encoding="utf-8"))
    if loaded is None:
        return []
    if not isinstance(loaded, list):
        raise ValueError(f"{binds_path} must contain a YAML array.")

    binds: list[dict[str, str]] = []
    for item in loaded:
        if not isinstance(item, dict):
            raise ValueError(f"{binds_path} entries must be YAML objects.")
        bind = item.get("Bind")
        domain = item.get("Domain")
        if not isinstance(bind, str) or not isinstance(domain, str):
            raise ValueError(f"{binds_path} entries must contain string Bind and Domain.")
        entry = {"Bind": bind, "Domain": domain}
        schema = item.get(BIND_SCHEMA_KEY)
        if schema is not None:
            if not isinstance(schema, str):
                raise ValueError(
                    f"{binds_path} Schema values must be strings when present."
                )
            entry[BIND_SCHEMA_KEY] = schema
        binds.append(entry)
    return binds


def get_binds_log_path(binds_path: Path) -> Path:
    """Return the wallet-managed bind-change log path for one binds file."""

    return binds_path.with_name("binds.log")


def get_bind_change_script_path() -> str:
    """Return the current top-level script path for bind-change diagnostics."""

    script_path = sys.argv[0] if sys.argv else ""
    if script_path == "":
        return "<unknown>"

    try:
        return str(Path(script_path).expanduser().resolve())
    except OSError:
        return script_path


def get_bind_change_version() -> str:
    """Return the installed CLI version for bind-change diagnostics."""

    try:
        return get_installed_version(CLI_PACKAGE_NAME)
    except PackageNotFoundError:
        return "0+unknown"


def append_bind_change_log(
    binds_path: Path,
    domain: str,
    previous_entry: dict[str, str] | None,
    new_entry: dict[str, str]
) -> None:
    """Append one bind change entry to the local wallet log."""

    log_path = get_binds_log_path(binds_path)
    timestamp = datetime.now().astimezone().isoformat(timespec = "seconds")
    action = "updated" if previous_entry is not None else "created"
    lines = [
        f"[{timestamp}] {action} bind for {domain}",
        f"  binds_file: {binds_path}",
    ]

    if previous_entry is not None:
        lines.append(
            f"  previous_bind: {normalize_bind_value(previous_entry['Bind'])}")
        previous_schema = previous_entry.get(BIND_SCHEMA_KEY)
        if previous_schema is not None:
            lines.append(f"  previous_schema: {previous_schema}")

    lines.append(f"  new_bind: {normalize_bind_value(new_entry['Bind'])}")
    new_schema = new_entry.get(BIND_SCHEMA_KEY)
    if new_schema is not None:
        lines.append(f"  new_schema: {new_schema}")

    with log_path.open("a", encoding = "utf-8") as handle:
        handle.write("\n".join(lines))
        handle.write("\n")

    log_path.chmod(0o600)


def append_bind_alert_log(
    binds_path: Path,
    domain: str,
    previous_entry: dict[str, str],
    new_entry: dict[str, str],
    script_path: str,
    version: str
) -> None:
    """Append a high-signal alert entry for an unexpected bind change."""

    log_path = get_binds_log_path(binds_path)
    timestamp = datetime.now().astimezone().isoformat(timespec = "seconds")
    lines = [
        f"[{timestamp}] ALERT bind changed for {domain}",
        f"  binds_file: {binds_path}",
        f"  script_path: {script_path}",
        f"  version: {version}",
        f"  previous_bind: {normalize_bind_value(previous_entry['Bind'])}",
        f"  new_bind: {normalize_bind_value(new_entry['Bind'])}",
    ]
    previous_schema = previous_entry.get(BIND_SCHEMA_KEY)
    if previous_schema is not None:
        lines.append(f"  previous_schema: {previous_schema}")
    new_schema = new_entry.get(BIND_SCHEMA_KEY)
    if new_schema is not None:
        lines.append(f"  new_schema: {new_schema}")

    with log_path.open("a", encoding = "utf-8") as handle:
        handle.write("\n".join(lines))
        handle.write("\n")

    log_path.chmod(0o600)


def notify_bind_change(
    domain: str,
    previous_bind: str,
    new_bind: str
) -> None:
    """Attempt to raise a local OS notification for an unexpected bind change."""

    # Keep automated test runs quiet even when they intentionally exercise the
    # unexpected-bind-change path.
    if PYTEST_CURRENT_TEST_ENV in os.environ:
        return

    script = (
        'display notification '
        f'"Bind changed for {domain}\\n{previous_bind} -> {new_bind}" '
        f'with title "{MACOS_NOTIFICATION_TITLE}"'
    )
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check = False,
            stdout = subprocess.DEVNULL,
            stderr = subprocess.DEVNULL,
        )
    except OSError:
        return


def raise_bind_change_error(
    binds_path: Path,
    domain: str,
    previous_entry: dict[str, str],
    new_entry: dict[str, str]
) -> None:
    """Raise a discovery-time error when a domain bind unexpectedly changes."""

    previous_bind = normalize_bind_value(previous_entry["Bind"])
    new_bind = normalize_bind_value(new_entry["Bind"])
    script_path = get_bind_change_script_path()
    version = get_bind_change_version()
    append_bind_alert_log(
        binds_path,
        domain,
        previous_entry,
        new_entry,
        script_path,
        version)
    notify_bind_change(
        domain,
        previous_bind,
        new_bind)
    raise UserFacingError(
        "\n".join(
            [
                f"Bind changed unexpectedly for {domain}.",
                "The local bind was not updated so the churn can be investigated.",
                f"Previous bind: {previous_bind}",
                f"New bind: {new_bind}",
                f"Script path: {script_path}",
                f"Version: {version}",
                f"See {get_binds_log_path(binds_path)} for the alert entry.",
                (
                    "This usually means another process or concurrent test is "
                    "re-binding the same domain."
                ),
            ]
        )
    )


def save_bind(
    bind_entry: dict[str, str],
    domain: str,
    binds_path: Path
) -> None:
    """Store or replace the bind entry for a domain and schema combination."""

    normalized_domain = normalize_bind_domain(domain)
    binds = load_binds(binds_path)
    entry = {
        **bind_entry,
        "Bind": normalize_bind_value(bind_entry["Bind"]),
        "Domain": normalized_domain,
    }
    schema = entry.get(BIND_SCHEMA_KEY)
    previous_entry = next(
        (
            existing
            for existing in binds
            if existing["Domain"] == normalized_domain
            and existing.get(BIND_SCHEMA_KEY) == schema
        ),
        None)
    if (
        previous_entry is not None
        and normalize_bind_value(previous_entry["Bind"]) != entry["Bind"]
    ):
        raise_bind_change_error(
            binds_path,
            normalized_domain,
            previous_entry,
            entry)

    # Avoid rewriting the binds file or appending audit noise when the
    # canonical domain/schema already points at the same bind UUID.
    if previous_entry == entry:
        return

    binds = [
        existing
        for existing in binds
        if not (
            existing["Domain"] == normalized_domain
            and existing.get(BIND_SCHEMA_KEY) == schema
        )
    ]
    binds.append(entry)
    binds_path.write_text(yaml.safe_dump(binds, sort_keys=False), encoding="utf-8")
    binds_path.chmod(0o600)
    append_bind_change_log(
        binds_path,
        normalized_domain,
        previous_entry,
        entry)


def get_first_bind_for_domain(
    domain: str,
    binds: list[dict[str, str]]
) -> str | None:
    """Return the first stored bind token for a domain."""

    normalized_domain = normalize_bind_domain(domain)
    for bind in binds:
        if bind["Domain"] == normalized_domain:
            return bind["Bind"]
    return None


def send_bind_message(
    domain: str,
    key_pair: KeyPair,
    public_key_path: Path,
    binds_path: Path,
    debug: bool = False,
    debug_json: bool = False,
    anonymous: bool = False,
    unsigned: bool = False
) -> tuple[dict[str, str], str]:
    """Send the bind request for a domain and parse the server response."""

    normalized_domain = normalize_bind_domain(domain)
    public_key = serialize_public_key_value(
        public_key_path.read_text(encoding="utf-8")
    )
    payload, _, _ = send_wallet_message(
        domain=normalized_domain,
        subject=BIND_SUBJECT,
        body={
            "Domain": normalized_domain,
            "PublicKey": public_key,
        },
        key_pair=key_pair,
        debug=debug,
        debug_json=debug_json,
        binds_path=binds_path,
        anonymous=anonymous,
        unsigned=unsigned,
    )

    try:
        return parse_bind_response(payload), payload
    except UserFacingError as exc:
        raise UserFacingError(
            str(exc).replace("{domain}", normalized_domain)
        ) from None


def describe_bind_network_error(
    domain: str,
    reason: object
) -> str:
    """Convert bind transport failures into user-facing guidance."""

    normalized_domain = normalize_bind_domain(domain)
    if isinstance(reason, socket.gaierror):
        return (
            "Could not resolve PollyWeb inbox host "
            f"pw.{normalized_domain}. Check that the domain name is correct and that "
            "its DNS record exists."
        )

    if isinstance(reason, str):
        return reason

    return repr(reason)


def cmd_bind(
    domain: str,
    *,
    debug: bool,
    json_output: bool,
    config_dir: Path,
    public_key_path: Path,
    binds_path: Path,
    unsigned: bool,
    anonymous: bool,
    require_configured_keys,
    load_signing_key_pair
) -> int:
    """Run the bind command and persist the resulting bind token."""

    try:
        require_configured_keys()
        key_pair = load_signing_key_pair()
        bind_entry, raw_payload = send_bind_message(
            domain,
            key_pair,
            public_key_path,
            binds_path,
            debug=debug,
            debug_json=json_output,
            anonymous=anonymous,
            unsigned=unsigned,
        )
        save_bind(bind_entry, domain, binds_path)
    except FileNotFoundError:
        raise UserFacingError(
            f"Missing PollyWeb keys in {config_dir}. Run `pw config` first."
        ) from None
    except urllib.error.HTTPError as exc:
        raise UserFacingError(
            f"Could not bind {domain}. The server returned HTTP {exc.code}."
        ) from None
    except urllib.error.URLError as exc:
        reason = describe_bind_network_error(
            domain,
            exc.reason)
        raise UserFacingError(
            f"Could not bind {domain}. Network request failed: {reason}"
        ) from None

    if json_output:
        print(raw_payload)
        return 0

    print(f"Stored bind for {domain}: {normalize_bind_value(bind_entry['Bind'])}")
    print(f"Updated {binds_path}")
    return 0
