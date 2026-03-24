"""Configuration feature helpers and command implementation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
import socket
from urllib.parse import quote
import urllib.error
import uuid

import yaml
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from pollyweb import KeyPair, normalize_domain_name

from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.tools.debug import print_debug_payload
from pollyweb_cli.tools.transport import send_wallet_message
from pollyweb_cli.tools.debug import parse_debug_payload
from pollyweb_cli.tools.transport import rewrite_backend_validation_error
from pollyweb_cli.tools.transport import build_debug_http_error_payload

DEFAULT_NOTIFIER_DOMAIN = "any-notifier.pollyweb.org"
CONFIG_FILE_NAME = "config.yaml"
NOTIFIER_ONBOARD_SUBJECT = "Onboard@Notifier"


def write_config_file(
    config_path: Path,
    *,
    notifier_domain: str,
    wallet_id: str
) -> None:
    """Write the wallet configuration file to disk."""

    config_payload = {
        "Helpers": {
            "Notifier": normalize_domain_name(notifier_domain),
        },
        "Wallet": wallet_id,
    }
    config_path.write_text(
        yaml.safe_dump(config_payload, sort_keys = False),
        encoding = "utf-8")
    config_path.chmod(0o600)


def load_notifier_domain(
    config_path: Path
) -> str:
    """Load the notifier helper domain from config for chat-related commands."""

    if not config_path.exists():
        return DEFAULT_NOTIFIER_DOMAIN

    config_payload = yaml.safe_load(config_path.read_text(encoding = "utf-8")) or {}
    if not isinstance(config_payload, dict):
        return DEFAULT_NOTIFIER_DOMAIN

    helpers = config_payload.get("Helpers")
    if not isinstance(helpers, dict):
        return DEFAULT_NOTIFIER_DOMAIN

    notifier_domain = helpers.get("Notifier")
    if not isinstance(notifier_domain, str) or not notifier_domain.strip():
        return DEFAULT_NOTIFIER_DOMAIN

    return notifier_domain.strip()


def load_wallet_id_if_present(
    config_path: Path
) -> str | None:
    """Load the configured wallet id when it is present and non-empty."""

    if not config_path.exists():
        return None

    config_payload = yaml.safe_load(config_path.read_text(encoding = "utf-8")) or {}
    if not isinstance(config_payload, dict):
        return None

    wallet_id = config_payload.get("Wallet")
    if not isinstance(wallet_id, str) or not wallet_id.strip():
        return None

    return wallet_id.strip()


def serialize_public_key_value(public_key_pem: str) -> str:
    """Strip PEM framing so the public key can be sent in message bodies."""

    lines = [line.strip() for line in public_key_pem.splitlines() if line.strip()]
    return "".join(line for line in lines if not line.startswith("-----"))


def _extract_onboard_mapping(
    value: object
) -> dict[str, str] | None:
    """Walk a nested response payload and return the first wallet mapping."""

    if not isinstance(value, dict):
        return None

    wallet = value.get("Wallet")
    broker = value.get("Broker")

    if isinstance(wallet, str) and wallet.strip():
        entry = {"Wallet": wallet.strip()}
        if isinstance(broker, str) and broker.strip():
            entry["Broker"] = broker.strip()
        return entry

    for key in ("Response", "Body", "Request", "Header"):
        nested_value = value.get(key)
        nested_entry = _extract_onboard_mapping(nested_value)
        if nested_entry is not None:
            return nested_entry

    for nested_value in value.values():
        nested_entry = _extract_onboard_mapping(nested_value)
        if nested_entry is not None:
            return nested_entry

    return None


def parse_onboard_response(payload: str) -> dict[str, str]:
    """Extract the wallet registration details from one notifier response."""

    try:
        parsed_payload = json.loads(payload)
    except json.JSONDecodeError:
        parsed_payload = None

    if isinstance(parsed_payload, dict):
        onboard_entry = _extract_onboard_mapping(parsed_payload)
        if onboard_entry is not None:
            try:
                uuid.UUID(onboard_entry["Wallet"])
            except (ValueError, KeyError):
                raise UserFacingError(
                    "Notifier onboarding returned an invalid Wallet UUID."
                ) from None

            return onboard_entry

    preview = " ".join(payload.split())
    if len(preview) > 160:
        preview = preview[:157] + "..."

    raise UserFacingError(
        "\n".join(
            [
                "Could not register this wallet with the Notifier.",
                "The server replied, but it did not include a Wallet UUID.",
                (
                    f"Response preview: {preview}"
                    if preview
                    else "Response preview: <empty response>"
                ),
            ]
        )
    )


def describe_http_onboard_error(exc: urllib.error.HTTPError) -> str:
    """Build the user-facing HTTP failure message for notifier onboarding."""

    message = f"The notifier returned HTTP {exc.code} {exc.reason}."
    error_body = getattr(exc, "pollyweb_error_body", None)

    if not isinstance(error_body, str) or not error_body.strip():
        return message

    try:
        parsed_body = parse_debug_payload(error_body)
    except Exception:
        parsed_body = None

    if isinstance(parsed_body, dict):
        error_value = parsed_body.get("error")
        if isinstance(error_value, str) and error_value.strip():
            return (
                f"{message} "
                f"{rewrite_backend_validation_error(error_value)}"
            )

    return message


def describe_onboard_network_error(
    notifier_domain: str,
    reason: object
) -> str:
    """Convert notifier onboarding transport failures into user-facing guidance."""

    normalized_domain = normalize_domain_name(notifier_domain)

    if isinstance(reason, socket.gaierror):
        lookup_url = (
            "https://mxtoolbox.com/SuperTool.aspx?action="
            f"{quote(f'a:pw.{normalized_domain}')}&run=toolpage"
        )
        return (
            f"No DNS entry found for domain {normalized_domain}. "
            f"See {lookup_url}"
        )

    if isinstance(reason, str):
        return reason

    return repr(reason)


def onboard_wallet_with_notifier(
    *,
    key_pair: KeyPair,
    public_key_path: Path,
    notifier_domain: str,
    debug: bool = False
) -> dict[str, str]:
    """Register the wallet public key with the configured notifier."""

    public_key = serialize_public_key_value(
        public_key_path.read_text(encoding = "utf-8")
    )
    response_payload, _, normalized_domain = send_wallet_message(
        domain = notifier_domain,
        subject = NOTIFIER_ONBOARD_SUBJECT,
        body = {
            "PublicKey": public_key,
        },
        key_pair = key_pair,
        debug = debug,
    )
    onboard_entry = parse_onboard_response(response_payload)
    onboard_entry["Notifier"] = normalized_domain
    return onboard_entry


def require_configured_keys(
    config_dir: Path,
    private_key_path: Path,
    public_key_path: Path
) -> None:
    """Ensure the wallet keypair exists before running commands that need it."""

    if private_key_path.exists() and public_key_path.exists():
        return
    raise FileNotFoundError(
        f"Missing PollyWeb keys in {config_dir}. Run `pw config` first."
    )


def load_signing_key_pair(private_key_path: Path) -> KeyPair:
    """Load the configured private key and wrap it in a PollyWeb keypair object."""

    private_key = load_pem_private_key(private_key_path.read_bytes(), password=None)
    return KeyPair(PrivateKey=private_key)


def cmd_config(
    *,
    force: bool,
    debug: bool,
    config_dir: Path,
    private_key_path: Path,
    public_key_path: Path,
    config_path: Path
) -> int:
    """Create or reuse the local wallet keypair and notifier registration."""

    private_exists = private_key_path.exists()
    public_exists = public_key_path.exists()
    config_exists = config_path.exists()
    notifier_domain = load_notifier_domain(config_path)
    configured_wallet_id = load_wallet_id_if_present(config_path)

    if not force and private_exists and public_exists and config_exists:
        print(f"Using existing {private_key_path}")
        print(f"Using existing {public_key_path}")
        key_pair = load_signing_key_pair(private_key_path)
    elif not force and (private_exists or public_exists or config_exists):
        print(
            "Wallet files are only partially configured. Re-run with --force to recreate them.",
            file=sys.stderr,
        )
        return 1
    else:
        config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

        # Generate a fresh wallet key pair before contacting the notifier.
        key_pair = KeyPair()
        private_pem = key_pair.private_pem_bytes()
        public_pem = key_pair.public_pem_bytes()
        private_key_path.write_bytes(private_pem)
        public_key_path.write_bytes(public_pem)
        private_key_path.chmod(0o600)
        public_key_path.chmod(0o644)

        print(f"Created {private_key_path}")
        print(f"Created {public_key_path}")

    try:
        onboard_entry = onboard_wallet_with_notifier(
            key_pair = key_pair,
            public_key_path = public_key_path,
            notifier_domain = notifier_domain,
            debug = debug,
        )
    except urllib.error.HTTPError as exc:
        error_body = getattr(exc, "pollyweb_error_body", None)
        debug_payload_was_printed = bool(
            getattr(exc, "pollyweb_debug_error_payload_printed", False)
        )

        if (
            debug
            and not debug_payload_was_printed
            and isinstance(error_body, str)
            and error_body.strip()
        ):
            print_debug_payload(
                "Inbound payload",
                build_debug_http_error_payload(error_body))

        if debug and isinstance(error_body, str) and error_body.strip():
            raise UserFacingError(
                "\n".join(
                    [
                        "Could not register this wallet with the Notifier.",
                        describe_http_onboard_error(exc),
                        "Full error body:",
                        error_body,
                    ]
                )
            ) from None

        raise UserFacingError(
            f"Could not register this wallet with the Notifier. {describe_http_onboard_error(exc)}"
        ) from None
    except urllib.error.URLError as exc:
        reason = describe_onboard_network_error(
            notifier_domain,
            exc.reason)
        raise UserFacingError(
            f"Could not register this wallet with the Notifier. Network request failed: {reason}"
        ) from None
    except OSError as exc:
        reason = describe_onboard_network_error(
            notifier_domain,
            exc)
        raise UserFacingError(
            f"Could not register this wallet with the Notifier. Network request failed: {reason}"
        ) from None

    if (
        configured_wallet_id is not None
        and configured_wallet_id != onboard_entry["Wallet"]
    ):
        raise UserFacingError(
            "\n".join(
                [
                    "Wallet registration drift detected.",
                    f"Configured Wallet: {configured_wallet_id}",
                    f"Notifier Wallet: {onboard_entry['Wallet']}",
                    "The same key pair should return the same wallet id on every `Onboard@Notifier` call.",
                ]
            )
        )

    write_config_file(
        config_path,
        notifier_domain = onboard_entry["Notifier"],
        wallet_id = onboard_entry["Wallet"],
    )
    print(f"Created {config_path}" if force or not config_exists else f"Using existing {config_path}")
    print(f"✅ Registered with Notifier: {onboard_entry['Notifier']}")

    return 0
