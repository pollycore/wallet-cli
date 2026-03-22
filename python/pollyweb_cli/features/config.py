"""Configuration feature helpers and command implementation."""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import yaml
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from pollyweb import KeyPair, Msg

from pollyweb_cli.features.bind import serialize_public_key_value
from pollyweb_cli.tools.debug import parse_debug_payload, print_debug_payload


NOTIFIER_DOMAIN = "any-notifier.pollyweb.org"
NOTIFIER_SUBJECT = "Onboard@Notifier"
NOTIFIER_LANGUAGE = "en-us"
CONFIG_FILE_NAME = "config.yaml"


def write_config_file(
    config_path: Path
) -> None:
    """Write the default wallet helper configuration to disk."""

    # Store the notifier helper in YAML so later commands can reuse it.
    config_payload = {
        "Helpers": {
            "Notifier": NOTIFIER_DOMAIN,
        }
    }
    config_path.write_text(
        yaml.safe_dump(
            config_payload,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    config_path.chmod(0o600)


def save_onboarded_wallet_config(
    config_path: Path,
    broker_domain: str | None = None,
    wallet_id: str | None = None
) -> None:
    """Persist onboarding metadata in the wallet configuration file."""

    if not broker_domain and not wallet_id:
        return

    # Load the existing YAML so notifier settings stay intact.
    config_payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(config_payload, dict):
        config_payload = {}

    helpers = config_payload.get("Helpers")
    if not isinstance(helpers, dict):
        helpers = {}
        config_payload["Helpers"] = helpers

    # Record the broker returned by onboarding for later wallet commands.
    if broker_domain:
        helpers["Broker"] = broker_domain

    # Store the assigned wallet ID so later commands can reuse it.
    if wallet_id:
        config_payload["Wallet"] = wallet_id

    config_path.write_text(
        yaml.safe_dump(
            config_payload,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    config_path.chmod(0o600)


def load_notifier_domain(
    config_path: Path
) -> str:
    """Load the notifier helper domain from the wallet configuration file."""

    if not config_path.exists():
        return NOTIFIER_DOMAIN

    # Fall back to the default helper if the YAML file is empty or partial.
    config_payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(config_payload, dict):
        return NOTIFIER_DOMAIN

    helpers = config_payload.get("Helpers")
    if not isinstance(helpers, dict):
        return NOTIFIER_DOMAIN

    notifier_domain = helpers.get("Notifier")
    if not isinstance(notifier_domain, str) or not notifier_domain:
        return NOTIFIER_DOMAIN

    return notifier_domain


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


def send_onboard_message(
    key_pair: KeyPair,
    public_key: bytes,
    notifier_domain: str,
    debug: bool = False
) -> dict[str, object]:
    """Send an onboarding request for the wallet public key."""

    # Send only the compact public key value, not the PEM envelope lines.
    public_key_value = serialize_public_key_value(public_key.decode("ascii"))

    msg = Msg(
        From="Anonymous",
        To=notifier_domain,
        Subject=NOTIFIER_SUBJECT,
        Body={
            "Language": NOTIFIER_LANGUAGE,
            "PublicKey": public_key_value,
        },
    )

    # PollyWeb wallets cannot sign as Anonymous, so onboarding stays as the
    # unsigned anonymous request that the notifier already accepts.
    payload = msg.to_dict()

    if debug:
        print_debug_payload(
            f"Outbound payload to https://pw.{notifier_domain}/inbox",
            payload,
        )

    request = urllib.request.Request(
        f"https://pw.{notifier_domain}/inbox",
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request) as response:
        payload = response.read()

    if not payload:
        if debug:
            print_debug_payload("Inbound payload", {})
        return {}

    if debug:
        print_debug_payload("Inbound payload", parse_debug_payload(payload.decode("utf-8")))

    result = json.loads(payload)
    if not isinstance(result, dict):
        raise ValueError("Notifier onboard response must be a JSON object.")
    return result


def cmd_config(
    *,
    force: bool,
    debug: bool,
    config_dir: Path,
    private_key_path: Path,
    public_key_path: Path,
    config_path: Path
) -> int:
    """Create or reuse the local wallet keypair."""

    private_exists = private_key_path.exists()
    public_exists = public_key_path.exists()
    config_exists = config_path.exists()

    if not force and private_exists and public_exists and config_exists:
        print(f"Using existing {private_key_path}")
        print(f"Using existing {public_key_path}")
        print(f"Using existing {config_path}")
        return 0

    if not force and (private_exists or public_exists or config_exists):
        print(
            "Wallet files are only partially configured. Re-run with --force to recreate them.",
            file=sys.stderr,
        )
        return 1

    config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    key_pair = KeyPair()
    private_pem = key_pair.private_pem_bytes()
    public_pem = key_pair.public_pem_bytes()
    private_key_path.write_bytes(private_pem)
    public_key_path.write_bytes(public_pem)
    private_key_path.chmod(0o600)
    public_key_path.chmod(0o644)
    write_config_file(config_path)

    print(f"Created {private_key_path}")
    print(f"Created {public_key_path}")
    print(f"Created {config_path}")

    # Treat notifier registration as best-effort so local setup stays reliable.
    try:
        notifier_domain = load_notifier_domain(config_path)
        onboard_response = send_onboard_message(
            key_pair,
            public_pem,
            notifier_domain,
            debug=debug,
        )
        broker_domain = onboard_response.get("Broker")
        wallet = onboard_response.get("Wallet")
        if (
            isinstance(broker_domain, str)
            and broker_domain
        ) or (
            isinstance(wallet, str)
            and wallet
        ):
            save_onboarded_wallet_config(
                config_path,
                broker_domain=broker_domain if isinstance(broker_domain, str) else None,
                wallet_id=wallet if isinstance(wallet, str) else None,
            )
        if wallet:
            print(f"Wallet: {wallet}")
    except Exception:
        pass

    return 0
