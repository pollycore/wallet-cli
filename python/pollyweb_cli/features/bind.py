"""Bind feature helpers and command implementation."""

from __future__ import annotations

import json
import re
import socket
import sys
import urllib.error
from pathlib import Path

import yaml
from pollyweb import KeyPair

from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.tools.transport import post_signed_message


BIND_SUBJECT = "Bind@Vault"
BIND_SCHEMA_KEY = "Schema"
BIND_PATTERN = re.compile(
    r"Bind:[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}"
)


def serialize_public_key_value(public_key_pem: str) -> str:
    """Strip PEM framing so the public key can be sent in message bodies."""

    lines = [line.strip() for line in public_key_pem.splitlines() if line.strip()]
    return "".join(line for line in lines if not line.startswith("-----"))


def parse_bind_response(payload: str) -> dict[str, str]:
    """Extract the bind token and optional schema from a bind response."""

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
                    "Could not bind {domain}.",
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


def save_bind(
    bind_entry: dict[str, str],
    domain: str,
    binds_path: Path
) -> None:
    """Store or replace the bind entry for a domain and schema combination."""

    binds = load_binds(binds_path)
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
    binds_path.write_text(yaml.safe_dump(binds, sort_keys=False), encoding="utf-8")
    binds_path.chmod(0o600)


def get_first_bind_for_domain(
    domain: str,
    binds: list[dict[str, str]]
) -> str | None:
    """Return the first stored bind token for a domain."""

    for bind in binds:
        if bind["Domain"] == domain:
            return bind["Bind"]
    return None


def send_bind_message(
    domain: str,
    key_pair: KeyPair,
    public_key_path: Path,
    debug: bool = False
) -> dict[str, str]:
    """Send the bind request for a domain and parse the server response."""

    public_key = serialize_public_key_value(
        public_key_path.read_text(encoding="utf-8")
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
        return parse_bind_response(payload)
    except UserFacingError as exc:
        raise UserFacingError(str(exc).replace("{domain}", domain)) from None


def describe_bind_network_error(
    domain: str,
    reason: object
) -> str:
    """Convert bind transport failures into user-facing guidance."""

    if isinstance(reason, socket.gaierror):
        return (
            "Could not resolve PollyWeb inbox host "
            f"pw.{domain}. Check that the domain name is correct and that "
            "its DNS record exists."
        )

    if isinstance(reason, str):
        return reason

    return repr(reason)


def cmd_bind(
    domain: str,
    *,
    debug: bool,
    config_dir: Path,
    public_key_path: Path,
    binds_path: Path,
    require_configured_keys,
    load_signing_key_pair
) -> int:
    """Run the bind command and persist the resulting bind token."""

    try:
        require_configured_keys()
        key_pair = load_signing_key_pair()
        bind_entry = send_bind_message(
            domain,
            key_pair,
            public_key_path,
            debug=debug,
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

    print(f"Stored bind for {domain}: {bind_entry['Bind']}")
    print(f"Updated {binds_path}")
    return 0
