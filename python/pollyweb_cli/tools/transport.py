"""Wallet-backed message helpers shared by CLI commands."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import uuid

from pollyweb import KeyPair, Msg, Wallet, normalize_domain_name
import yaml

from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.tools.debug import parse_debug_payload, print_debug_payload


DEFAULT_SCHEMA = "pollyweb.org/MSG:1.0"
DEFAULT_BINDS_PATH = Path.home() / ".pollyweb" / "binds.yaml"


def serialize_wallet_response(response: object) -> str:
    """Convert a PollyWeb response object into the CLI's raw string form."""

    if isinstance(response, Msg):
        return json.dumps(response.to_dict(), separators=(",", ":"))
    if isinstance(response, dict):
        return json.dumps(response, separators=(",", ":"))
    return str(response)


def build_debug_outbound_payload(
    wallet: Wallet,
    request_message: Msg,
    *,
    unsigned: bool = False
) -> dict[str, object]:
    """Render the actual outbound payload shape used by `wallet.send()`."""

    outbound_message = build_wallet_outbound_message(
        wallet,
        request_message,
        unsigned = unsigned)

    return outbound_message.to_dict()


def build_wallet_outbound_message(
    wallet: Wallet,
    request_message: Msg,
    *,
    unsigned: bool = False
) -> Msg:
    """Build the concrete outbound message for the current wallet mode."""

    if unsigned:
        return replace(
            request_message,
            From = wallet.ID,
            Selector = "",
            Algorithm = "",
            Hash = None,
            Signature = None)

    if wallet.ID == "Anonymous":
        return request_message

    return wallet.sign(request_message)


def _load_first_bind_for_domain(
    domain: str,
    binds_path: Path
) -> str | None:
    """Return the first stored bind UUID for a normalized domain."""

    if not binds_path.exists():
        return None

    loaded = yaml.safe_load(binds_path.read_text(encoding = "utf-8"))
    if not isinstance(loaded, list):
        return None

    normalized_domain = normalize_domain_name(domain)

    # Reuse the canonical recipient domain so `.dom` and `.pollyweb.org`
    # lookups find the same stored bind entry.
    for item in loaded:
        if not isinstance(item, dict):
            continue

        bind_value = item.get("Bind")
        bind_domain = item.get("Domain")

        if not isinstance(bind_value, str) or not isinstance(bind_domain, str):
            continue

        try:
            uuid.UUID(bind_value)
        except (ValueError, AttributeError, TypeError):
            continue

        if normalize_domain_name(bind_domain) == normalized_domain:
            return bind_value

    return None


def _resolve_wallet_sender(
    domain: str,
    from_value: str | None,
    binds_path: Path,
    *,
    anonymous: bool = False
) -> str | None:
    """Choose the wallet sender ID, preferring a stored bind over an empty sender."""

    if anonymous:
        return None

    if from_value not in (None, "", "Anonymous"):
        return str(from_value)

    stored_bind = _load_first_bind_for_domain(domain, binds_path)
    if stored_bind:
        return stored_bind

    if from_value == "Anonymous":
        return None

    return None


def build_wallet_message(
    domain: str,
    subject: str,
    body: dict[str, object],
    key_pair: KeyPair,
    from_value: str | None = "Anonymous",
    schema_value: str | None = DEFAULT_SCHEMA,
    binds_path: Path | None = None,
    anonymous: bool = False
) -> tuple[Wallet, Msg, str]:
    """Create a wallet sender and normalized PollyWeb message."""

    normalized_domain = normalize_domain_name(domain)
    effective_binds_path = DEFAULT_BINDS_PATH if binds_path is None else binds_path
    sender_value = _resolve_wallet_sender(
        normalized_domain,
        from_value,
        effective_binds_path,
        anonymous = anonymous,
    )

    try:
        wallet_kwargs = {"KeyPair": key_pair}
        if sender_value is not None:
            wallet_kwargs["ID"] = sender_value

        wallet = Wallet(**wallet_kwargs)
    except ValueError:
        raise UserFacingError(
            "Wallet-backed commands only support `From: Anonymous` or a UUID bind value."
        ) from None

    message_kwargs: dict[str, object] = {
        "To": normalized_domain,
        "Subject": subject,
        "Body": body,
    }
    if schema_value is not None:
        message_kwargs["Schema"] = schema_value

    return wallet, Msg(**message_kwargs), normalized_domain


def send_wallet_message(
    domain: str,
    subject: str,
    body: dict[str, object],
    key_pair: KeyPair,
    debug: bool = False,
    from_value: str | None = "Anonymous",
    schema_value: str | None = DEFAULT_SCHEMA,
    binds_path: Path | None = None,
    anonymous: bool = False,
    unsigned: bool = False
) -> tuple[str, Msg, str]:
    """Send one wallet-backed PollyWeb message and return the raw response."""

    wallet, request_message, normalized_domain = build_wallet_message(
        domain=domain,
        subject=subject,
        body=body,
        key_pair=key_pair,
        from_value=from_value,
        schema_value=schema_value,
        binds_path=binds_path,
        anonymous=anonymous,
    )

    if debug:
        request_url = f"https://pw.{normalized_domain}/inbox"
        print_debug_payload(
            f"Outbound payload to {request_url}",
            build_debug_outbound_payload(
                wallet,
                request_message,
                unsigned = unsigned),
        )

    outbound_message = build_wallet_outbound_message(
        wallet,
        request_message,
        unsigned = unsigned)
    response = outbound_message.send()
    response_payload = serialize_wallet_response(response)

    if debug:
        print_debug_payload("Inbound payload", parse_debug_payload(response_payload))

    return response_payload, request_message, normalized_domain
