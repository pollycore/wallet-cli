from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from pollyweb import KeyPair, Msg


CONFIG_DIR = Path.home() / ".pollyweb"
PRIVATE_KEY_PATH = CONFIG_DIR / "private.pem"
PUBLIC_KEY_PATH = CONFIG_DIR / "public.pem"
BINDS_PATH = CONFIG_DIR / "binds.yaml"
BIND_SUBJECT = "Bind@Vault"
SHELL_SUBJECT = "Shell@Domain"
BIND_PATTERN = re.compile(
    r"Bind:[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}"
)


class UserFacingError(Exception):
    """A concise error intended to be shown directly to CLI users."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pw",
        description="PollyWeb command line wallet.",
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

    shell_parser = subparsers.add_parser(
        "shell",
        help="Open an interactive shell against a domain.",
    )
    shell_parser.add_argument(
        "domain", help="Domain that will receive shell commands."
    )

    return parser

def require_configured_keys() -> None:
    if PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists():
        return
    raise FileNotFoundError(
        f"Missing PollyWeb keys in {CONFIG_DIR}. Run `pw config` first."
    )


def load_signing_key_pair() -> KeyPair:
    private_key = load_pem_private_key(PRIVATE_KEY_PATH.read_bytes(), password=None)
    return KeyPair(PrivateKey=private_key)


def send_bind_message(domain: str, key_pair: KeyPair, debug: bool = False) -> str:
    public_key = PUBLIC_KEY_PATH.read_text(encoding="utf-8")
    payload = post_signed_message(
        domain=domain,
        subject=BIND_SUBJECT,
        body={"PublicKey": public_key},
        key_pair=key_pair,
        debug=debug,
    )

    match = BIND_PATTERN.search(payload)
    if match is None:
        preview = " ".join(payload.split())
        if len(preview) > 160:
            preview = preview[:157] + "..."
        raise UserFacingError(
            "\n".join(
                [
                    f"Could not bind {domain}.",
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
    return match.group(0)


def post_signed_message(
    domain: str,
    subject: str,
    body: dict[str, object],
    key_pair: KeyPair,
    debug: bool = False,
) -> str:
    message = Msg(
        From="Anonymous",
        To=domain,
        Subject=subject,
        Body=body,
    ).sign(key_pair.PrivateKey)
    request_payload = json.dumps(message.to_dict(), separators=(",", ":"))

    if debug:
        print("Outbound payload:")
        print(request_payload)

    request = urllib.request.Request(
        f"https://pw.{domain}/inbox",
        data=request_payload.encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        response_payload = response.read().decode("utf-8")

    if debug:
        print("Inbound payload:")
        print(response_payload)

    return response_payload


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
        binds.append({"Bind": bind, "Domain": domain})
    return binds


def save_bind(bind_value: str, domain: str) -> None:
    binds = load_binds()
    entry = {"Bind": bind_value, "Domain": domain}
    if entry not in binds:
        binds.append(entry)
    BINDS_PATH.write_text(yaml.safe_dump(binds, sort_keys=False), encoding="utf-8")
    BINDS_PATH.chmod(0o600)


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
    return 0


def cmd_bind(domain: str, debug: bool = False) -> int:
    try:
        require_configured_keys()
        key_pair = load_signing_key_pair()
        bind_value = send_bind_message(domain, key_pair, debug=debug)
        save_bind(bind_value, domain)
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

    print(f"Stored bind for {domain}: {bind_value}")
    print(f"Updated {BINDS_PATH}")
    return 0


def cmd_shell(domain: str) -> int:
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

        try:
            response = post_signed_message(
                domain=domain,
                subject=SHELL_SUBJECT,
                body={"Binds": binds, "Command": command},
                key_pair=key_pair,
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

        print(response)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "config":
            return cmd_config(force=args.force)
        if args.command == "bind":
            return cmd_bind(domain=args.domain, debug=args.debug)
        if args.command == "shell":
            return cmd_shell(domain=args.domain)
    except UserFacingError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
