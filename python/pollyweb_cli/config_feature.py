"""Configuration feature helpers and command implementation."""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from pollyweb import KeyPair, Msg


NOTIFIER_DOMAIN = "any-notifier.pollyweb.org"
NOTIFIER_SUBJECT = "Onboard@Notifier"
NOTIFIER_LANGUAGE = "en-us"


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


def send_onboard_message(public_key: bytes) -> dict[str, object]:
    """Send an onboarding request for the wallet public key."""

    msg = Msg(
        To=NOTIFIER_DOMAIN,
        Subject=NOTIFIER_SUBJECT,
        Body={
            "Language": NOTIFIER_LANGUAGE,
            "PublicKey": public_key.decode("ascii"),
        },
    )
    request = urllib.request.Request(
        f"https://pw.{NOTIFIER_DOMAIN}/inbox",
        data=json.dumps(msg.to_dict(), separators=(",", ":")).encode("utf-8"),
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


def cmd_config(
    *,
    force: bool,
    config_dir: Path,
    private_key_path: Path,
    public_key_path: Path
) -> int:
    """Create or reuse the local wallet keypair."""

    private_exists = private_key_path.exists()
    public_exists = public_key_path.exists()

    if not force and private_exists and public_exists:
        print(f"Using existing {private_key_path}")
        print(f"Using existing {public_key_path}")
        return 0

    if not force and (private_exists or public_exists):
        print(
            "Key files are only partially configured. Re-run with --force to recreate them.",
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

    print(f"Created {private_key_path}")
    print(f"Created {public_key_path}")

    # Treat notifier registration as best-effort so local setup stays reliable.
    try:
        onboard_response = send_onboard_message(public_pem)
        if wallet := onboard_response.get("Wallet"):
            print(f"Wallet: {wallet}")
    except Exception:
        pass

    return 0
