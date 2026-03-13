from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pollyweb import KeyPair


CONFIG_DIR = Path.home() / ".pollyweb"
PRIVATE_KEY_PATH = CONFIG_DIR / "private.pem"
PUBLIC_KEY_PATH = CONFIG_DIR / "public.pem"


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

    return parser


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
    PRIVATE_KEY_PATH.write_bytes(key_pair.private_pem_bytes())
    PUBLIC_KEY_PATH.write_bytes(key_pair.public_pem_bytes())
    PRIVATE_KEY_PATH.chmod(0o600)
    PUBLIC_KEY_PATH.chmod(0o644)

    print(f"Created {PRIVATE_KEY_PATH}")
    print(f"Created {PUBLIC_KEY_PATH}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "config":
        return cmd_config(force=args.force)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
